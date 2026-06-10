"""SEC EDGAR watchlist feed: pull a company's recent filings into the system.

Uses the public submissions API (`data.sec.gov/submissions/CIK##########.json`)
to list filings, filters to 10-K/10-Q (and their /A amendments), downloads each
primary document (native HTML — exactly what the built-in parser handles), and
runs it through the FinancialIngestor. Downloads are cached under
`data/edgar/<entity>/` so the same files can be narratively indexed with the
regular `make ingest SOURCE=...`.

SEC's fair-access policy requires a descriptive User-Agent with contact info
(EDGAR_USER_AGENT, e.g. "Acme Internal RAG admin@acme.com") and modest request
rates — this module is a low-volume watchlist sync, not a crawler. The HTTP
transport is injectable, so tests run on fixtures with no network.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from app.core.finance import SourceAuthority
from app.core.models import DocRef

from ingestion.pipeline.financial import FinancialIngestor, FinancialIngestSummary

logger = logging.getLogger("rag.edgar")

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"

_FORM_AUTHORITY: dict[str, SourceAuthority] = {
    "10-K": SourceAuthority.ANNUAL_FILING,
    "10-Q": SourceAuthority.QUARTERLY_FILING,
    "10-K/A": SourceAuthority.AMENDMENT,
    "10-Q/A": SourceAuthority.AMENDMENT,
}

# fetch(url) -> response body bytes
Fetch = Callable[[str], Awaitable[bytes]]


@dataclass(slots=True)
class EdgarFiling:
    form: str  # "10-K" | "10-Q" | "10-K/A" | "10-Q/A"
    accession: str  # e.g. "0000320193-24-000123"
    primary_doc: str  # e.g. "aapl-20240928.htm"
    filed: date

    @property
    def authority(self) -> SourceAuthority:
        return _FORM_AUTHORITY[self.form]


def recent_filings(submissions: dict[str, Any], limit: int = 4) -> list[EdgarFiling]:
    """The newest financial filings from a submissions payload (newest first)."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    dates = recent.get("filingDate", [])

    filings: list[EdgarFiling] = []
    # strict=False: EDGAR's parallel arrays are equal-length by contract, but a
    # truncated payload should degrade to fewer filings, not crash the sync.
    for form, accession, doc, filed in zip(
        forms, accessions, docs, dates, strict=False
    ):
        if form not in _FORM_AUTHORITY or not doc:
            continue
        filings.append(
            EdgarFiling(
                form=form,
                accession=accession,
                primary_doc=doc,
                filed=date.fromisoformat(filed),
            )
        )
        if len(filings) >= limit:
            break
    return filings


class EdgarClient:
    def __init__(self, user_agent: str, fetch: Fetch | None = None) -> None:
        if not user_agent:
            raise ValueError(
                "EDGAR_USER_AGENT is required (SEC fair-access policy): a "
                'descriptive string with contact info, e.g. "Acme RAG ops@acme.com".'
            )
        self._headers = {"User-Agent": user_agent}
        self._fetch = fetch or self._http_fetch

    async def _http_fetch(self, url: str) -> bytes:
        async with httpx.AsyncClient(
            headers=self._headers, timeout=30, follow_redirects=True
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def submissions(self, cik: int) -> dict[str, Any]:
        import json

        return json.loads(await self._fetch(SUBMISSIONS_URL.format(cik=cik)))

    async def download(self, cik: int, filing: EdgarFiling) -> bytes:
        url = ARCHIVE_URL.format(
            cik=cik, accession=filing.accession.replace("-", ""),
            doc=filing.primary_doc,
        )
        return await self._fetch(url)


def _filetype(doc_name: str) -> str:
    ext = doc_name.rsplit(".", 1)[-1].lower() if "." in doc_name else ""
    return "html" if ext in {"htm", "html"} else ext


def fiscal_year_end_month(submissions: dict[str, Any]) -> int:
    """The entity's fiscal-year-end month from EDGAR's "MMDD" field
    (e.g. "0928" → 9). Calendar (12) when absent/malformed."""
    raw = submissions.get("fiscalYearEnd") or ""
    try:
        month = int(str(raw)[:2])
    except ValueError:
        return 12
    return month if 1 <= month <= 12 else 12


async def sync_entity(
    client: EdgarClient,
    ingestor: FinancialIngestor,
    entity_id: str,
    cik: int,
    entity_name: str | None = None,
    limit: int = 4,
    cache_dir: Path | None = None,
) -> list[FinancialIngestSummary]:
    """Pull the newest filings for one watchlist entity and ingest their facts.

    Filing form + filed date come from EDGAR metadata (authoritative — drives
    the restatement precedence), not from filename inference.
    """
    submissions = await client.submissions(cik)
    name = entity_name or submissions.get("name") or entity_id
    fye_month = fiscal_year_end_month(submissions)  # offset-FYE auto-detect
    filings = recent_filings(submissions, limit=limit)
    logger.info(
        "edgar: %s (CIK %d): %d filing(s) to ingest (FYE month %d)",
        entity_id, cik, len(filings), fye_month,
    )

    summaries: list[FinancialIngestSummary] = []
    for filing in filings:
        content = await client.download(cik, filing)

        if cache_dir is not None:
            target = cache_dir / entity_id / f"{filing.accession}_{filing.primary_doc}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        ref = DocRef(
            doc_id=f"{entity_id}-{filing.accession}",
            source_url=ARCHIVE_URL.format(
                cik=cik, accession=filing.accession.replace("-", ""),
                doc=filing.primary_doc,
            ),
            filetype=_filetype(filing.primary_doc),
        )
        summary = await ingestor.ingest(
            ref,
            content,
            entity_id,
            name,
            doc_type=filing.form,
            filed_date=filing.filed,
            fye_month=fye_month,
        )
        summaries.append(summary)
    return summaries
