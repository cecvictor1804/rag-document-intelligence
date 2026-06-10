"""Worker financial path: entity-from-key convention + concurrent ingestion."""

from __future__ import annotations

from pathlib import Path

from app.extraction.html_table import HtmlTableParser
from test_financial_ingest import RecordingStore

from ingestion.pipeline.financial import FinancialIngestor
from ingestion.pipeline.worker import _entity_for_key, handle_financial

SAMPLE = Path(__file__).resolve().parents[2] / "sample_docs" / "acme_corp_10q_q3_2024.html"


def test_entity_for_key_convention():
    assert _entity_for_key("ACME/acme_10q.html") == "ACME"
    assert _entity_for_key("acme_10q.html") is None  # no folder → narrative only
    assert _entity_for_key("ACME/sub/deep.html") is None  # one level only
    assert _entity_for_key("/orphan.html") is None
    assert _entity_for_key("ACME/") is None


async def test_handle_financial_ingests_foldered_keys_concurrently():
    fetched: list[str] = []

    async def fetch_bytes(key: str) -> bytes:
        fetched.append(key)
        return SAMPLE.read_bytes()

    store = RecordingStore()
    ingestor = FinancialIngestor(HtmlTableParser(), store)
    created = {
        "ACME/acme_10q_q3_2024.html",   # financial
        "BETA/beta_10q_q3_2024.html",   # financial, different entity
        "loose_note.html",              # no folder → skipped
    }

    n = await handle_financial(ingestor, fetch_bytes, created, concurrency=2)

    assert n == 2
    assert sorted(fetched) == [
        "ACME/acme_10q_q3_2024.html", "BETA/beta_10q_q3_2024.html",
    ]
    assert sorted(e for e, _ in store.entities) == ["ACME", "BETA"]
    assert len(store.facts) == 44  # 22 facts per filing


async def test_one_bad_document_does_not_stop_the_rest():
    async def fetch_bytes(key: str) -> bytes:
        if key.startswith("BAD/"):
            raise RuntimeError("s3 hiccup")
        return SAMPLE.read_bytes()

    store = RecordingStore()
    ingestor = FinancialIngestor(HtmlTableParser(), store)

    n = await handle_financial(
        ingestor, fetch_bytes,
        {"BAD/broken.html", "ACME/fine.html"}, concurrency=2,
    )

    assert n == 1
    assert [e for e, _ in store.entities] == ["ACME"]
