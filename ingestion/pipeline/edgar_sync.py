"""EDGAR watchlist sync CLI: pull a company's recent filings into the store.

Examples:
  python -m ingestion.pipeline.edgar_sync --entity AAPL --cik 320193 --limit 4
  make edgar-sync ENTITY=AAPL CIK=320193

Requires EDGAR_USER_AGENT in the environment (SEC fair-access policy) and a
migrated DB. Downloads are cached under data/edgar/<entity>/ so the same files
can be narratively indexed: make ingest SOURCE=data/edgar/<entity>.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from app.config import get_settings
from app.db.pool import close_pool
from app.extraction import build_financial_parser
from app.finance.store import PgMetricStore
from app.logging import configure_logging

from ingestion.pipeline.edgar import EdgarClient, sync_entity
from ingestion.pipeline.financial import FinancialIngestor

logger = logging.getLogger("rag.edgar")

DEFAULT_CACHE = Path("data/edgar")


async def _run(entity: str, cik: int, name: str | None, limit: int) -> int:
    settings = get_settings()
    client = EdgarClient(settings.edgar_user_agent)
    ingestor = FinancialIngestor(build_financial_parser(settings), PgMetricStore())

    try:
        summaries = await sync_entity(
            client, ingestor, entity, cik, name, limit=limit, cache_dir=DEFAULT_CACHE
        )
    finally:
        await close_pool()

    for summary in summaries:
        print(json.dumps(summary.as_dict(), indent=2))
    print(f"\nCached under {DEFAULT_CACHE / entity} — narratively index with:")
    print(f"  make ingest SOURCE={DEFAULT_CACHE / entity}")
    return 0 if summaries else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pull recent SEC filings for a watchlist entity into the metric store."
    )
    parser.add_argument("--entity", required=True, help="Entity id (e.g. ticker).")
    parser.add_argument("--cik", required=True, type=int, help="SEC CIK number.")
    parser.add_argument("--name", default=None, help="Entity display name.")
    parser.add_argument("--limit", default=4, type=int, help="Max filings to pull.")
    args = parser.parse_args()

    configure_logging(get_settings().log_level)
    raise SystemExit(asyncio.run(_run(args.entity, args.cik, args.name, args.limit)))


if __name__ == "__main__":
    main()
