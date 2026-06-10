"""EDGAR feed: filing selection from the submissions payload + a full sync
against fixture responses (no network)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from app.core.finance import SourceAuthority
from app.extraction.html_table import HtmlTableParser

from ingestion.pipeline.edgar import (
    ARCHIVE_URL,
    SUBMISSIONS_URL,
    EdgarClient,
    recent_filings,
    sync_entity,
)
from ingestion.pipeline.financial import FinancialIngestor

SAMPLE = Path(__file__).resolve().parents[2] / "sample_docs" / "acme_corp_10q_q3_2024.html"

SUBMISSIONS = {
    "name": "Acme Corp",
    "filings": {
        "recent": {
            # Mixed forms: only 10-K/10-Q(/A) should be selected, order kept.
            "form": ["8-K", "10-Q", "DEF 14A", "10-K/A", "10-K", "10-Q"],
            "accessionNumber": [
                "0000000000-24-000001", "0000000000-24-000002",
                "0000000000-24-000003", "0000000000-24-000004",
                "0000000000-24-000005", "0000000000-24-000006",
            ],
            "primaryDocument": [
                "ev.htm", "acme-10q.htm", "proxy.htm",
                "acme-10ka.htm", "acme-10k.htm", "acme-10q-old.htm",
            ],
            "filingDate": [
                "2024-11-01", "2024-10-30", "2024-09-01",
                "2024-08-15", "2024-02-01", "2023-10-28",
            ],
        }
    },
}


def test_recent_filings_filters_and_limits():
    filings = recent_filings(SUBMISSIONS, limit=3)
    assert [f.form for f in filings] == ["10-Q", "10-K/A", "10-K"]
    assert filings[0].filed == date(2024, 10, 30)
    assert filings[1].authority is SourceAuthority.AMENDMENT
    assert filings[2].authority is SourceAuthority.ANNUAL_FILING


def test_client_requires_user_agent():
    with pytest.raises(ValueError, match="EDGAR_USER_AGENT"):
        EdgarClient("")


class RecordingStore:
    def __init__(self) -> None:
        self.entities: list[tuple] = []
        self.documents: list = []
        self.facts: list = []

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


async def test_sync_entity_downloads_ingests_and_caches(tmp_path):
    requested: list[str] = []

    async def fetch(url: str) -> bytes:
        requested.append(url)
        if url == SUBMISSIONS_URL.format(cik=12345):
            return json.dumps(SUBMISSIONS).encode()
        return SAMPLE.read_bytes()  # every filing download serves the sample 10-Q

    client = EdgarClient("Acme RAG test@acme.com", fetch=fetch)
    store = RecordingStore()
    ingestor = FinancialIngestor(HtmlTableParser(), store)

    summaries = await sync_entity(
        client, ingestor, "ACME", 12345, limit=2, cache_dir=tmp_path
    )

    # Two filings ingested (10-Q + 10-K/A), facts extracted from each.
    assert len(summaries) == 2
    assert all(s.facts_upserted == 22 for s in summaries)
    assert all(s.reconciliation_issues == [] for s in summaries)

    # EDGAR metadata (form + filed date) drives the document record.
    assert store.documents[0].doc_type == "10-Q"
    assert store.documents[0].filed_date == date(2024, 10, 30)
    assert store.documents[1].doc_type == "10-K/A"
    assert store.documents[1].authority is SourceAuthority.AMENDMENT
    assert store.entities[0] == ("ACME", "Acme Corp")  # name from submissions

    # Download URL shape (accession without dashes) and local cache.
    expected_url = ARCHIVE_URL.format(
        cik=12345, accession="000000000024000002", doc="acme-10q.htm"
    )
    assert expected_url in requested
    cached = list((tmp_path / "ACME").iterdir())
    assert len(cached) == 2
