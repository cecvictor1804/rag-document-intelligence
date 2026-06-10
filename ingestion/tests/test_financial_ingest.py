"""Financial ingestor: parse → map → reconcile → store, plus an end-to-end run
over the sample 10-Q with the real HTML parser. Store is an in-memory fake."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.core.finance import (
    FinancialDocMeta,
    FinancialFact,
    ParsedFinancialDoc,
    ParsedTable,
    SourceAuthority,
)
from app.core.models import DocRef
from app.extraction.html_table import HtmlTableParser

from ingestion.pipeline.financial import FinancialIngestor, infer_doc_type

SAMPLE = Path(__file__).resolve().parents[2] / "sample_docs" / "acme_corp_10q_q3_2024.html"


class RecordingStore:
    def __init__(self) -> None:
        self.entities: list[tuple[str, str]] = []
        self.documents: list[FinancialDocMeta] = []
        self.facts: list[FinancialFact] = []

    async def upsert_entity(self, entity_id, name, ticker=None, cik=None):
        self.entities.append((entity_id, name))

    async def upsert_document(self, meta):
        self.documents.append(meta)

    async def upsert_facts(self, facts):
        self.facts.extend(facts)
        return len(facts)

    async def get_fact(self, *a, **k):  # pragma: no cover — protocol stub
        return None

    async def get_series(self, *a, **k):  # pragma: no cover — protocol stub
        return []


# ── doc-type inference ───────────────────────────────────────────────────────


def test_infer_doc_type_precedence():
    assert infer_doc_type("acme_10-K_2024.html") == ("10-K", SourceAuthority.ANNUAL_FILING)
    assert infer_doc_type("acme_10-q_q3.html") == ("10-Q", SourceAuthority.QUARTERLY_FILING)
    # Amendments outrank their base form and must match first.
    assert infer_doc_type("acme_10-K-A.html") == ("10-K/A", SourceAuthority.AMENDMENT)
    assert infer_doc_type("acme 10-Q/A.html") == ("10-Q/A", SourceAuthority.AMENDMENT)
    assert infer_doc_type("q3_earnings_release.html") == (
        "press_release", SourceAuthority.PRESS_RELEASE)
    assert infer_doc_type("acme_8-K.html") == ("press_release", SourceAuthority.PRESS_RELEASE)
    assert infer_doc_type("widget_strategy_memo.html") == ("other", SourceAuthority.OTHER)


# ── orchestration (fake parser) ──────────────────────────────────────────────


class FakeParser:
    name = "fake"

    def __init__(self, tables: list[ParsedTable]) -> None:
        self.tables = tables

    async def parse(self, ref, content):
        return ParsedFinancialDoc(ref=ref, title="t", text="", tables=self.tables)


def ref(doc_id: str = "acme_10-q_q3_2024.html") -> DocRef:
    return DocRef(doc_id=doc_id, source_url="file:///x", filetype="html")


async def test_ingest_surfaces_reconciliation_issues():
    # Balance sheet that does NOT balance: flagged, but still stored.
    bad_table = ParsedTable(
        index=0, caption="CONSOLIDATED BALANCE SHEETS (In millions)",
        rows=[
            ["", "September 30, 2024"],
            ["Total assets", "364,980"],
            ["Total liabilities", "308,030"],
            ["Total stockholders equity", "40,000"],
        ],
    )
    store = RecordingStore()
    ingestor = FinancialIngestor(FakeParser([bad_table]), store)

    summary = await ingestor.ingest(ref(), b"", "ACME", "Acme Corp")

    assert summary.facts_upserted == 3  # flagged != discarded
    assert len(summary.reconciliation_issues) == 1
    assert "balance_identity" in summary.reconciliation_issues[0]
    assert store.entities == [("ACME", "Acme Corp")]
    assert store.documents[0].doc_type == "10-Q"
    assert store.documents[0].authority is SourceAuthority.QUARTERLY_FILING


# ── end to end: real sample filing through the real HTML parser ─────────────


async def test_sample_10q_ingests_cleanly():
    store = RecordingStore()
    ingestor = FinancialIngestor(HtmlTableParser(), store)
    sample_ref = DocRef(
        doc_id=SAMPLE.name, source_url=SAMPLE.as_uri(), filetype="html"
    )

    summary = await ingestor.ingest(
        sample_ref, SAMPLE.read_bytes(), "ACME", "Acme Corp"
    )

    assert summary.doc_type == "10-Q"
    assert summary.tables_seen == 2
    assert summary.reconciliation_issues == []  # identities all hold
    assert summary.facts_upserted == 22  # 8 income rows x 2 periods + 6 balance
    assert summary.facts_mapped_canonical == 22  # every label in the chart

    by_key = {(f.line_item, f.period.label): f for f in store.facts}

    revenue = by_key[("revenue", "Q3 FY2024")]
    assert revenue.value == Decimal("94930") * 1_000_000  # scale normalized
    assert revenue.value_as_reported == Decimal("94930")
    assert revenue.line_item_as_reported == "Net sales"
    assert revenue.cell is not None and revenue.cell.table_index == 0

    assert by_key[("revenue", "Q3 FY2023")].value == Decimal("89498") * 1_000_000
    assert by_key[("eps_diluted", "Q3 FY2024")].value == Decimal("0.97")  # unscaled
    assert by_key[("total_equity", "Q3 FY2024")].value == Decimal("56950") * 1_000_000
