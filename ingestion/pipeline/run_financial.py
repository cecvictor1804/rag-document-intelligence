"""Financial ingestion CLI: extract facts from filings into the metric store.

Examples:
  python -m ingestion.pipeline.run_financial --entity ACME --name "Acme Corp" \\
      sample_docs/acme_corp_10q_q3_2024.html
  make ingest-financial ENTITY=ACME FILES=sample_docs/acme_corp_10q_q3_2024.html

Needs a migrated DB (make migrate). Re-running is idempotent: a document's
facts are replaced, not duplicated.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import date, datetime
from pathlib import Path

from app.config import get_settings
from app.core.models import DocRef
from app.db.pool import close_pool
from app.extraction import build_financial_parser
from app.finance.store import PgMetricStore
from app.logging import configure_logging

from ingestion.pipeline.financial import FinancialIngestor
from ingestion.pipeline.loaders import filetype_for

logger = logging.getLogger("rag.financial")


async def _run(
    files: list[str], entity: str, name: str | None, filed: date | None,
    fye_month: int,
) -> int:
    settings = get_settings()
    ingestor = FinancialIngestor(build_financial_parser(settings), PgMetricStore())

    failures = 0
    try:
        for raw_path in files:
            path = Path(raw_path)
            ref = DocRef(
                doc_id=path.name,
                source_url=path.resolve().as_uri(),
                filetype=filetype_for(path.name),
            )
            try:
                summary = await ingestor.ingest(
                    ref, path.read_bytes(), entity, name, filed_date=filed,
                    fye_month=fye_month,
                )
            except Exception as exc:  # noqa: BLE001 — report and continue
                logger.error("failed to ingest %s: %s", path, exc)
                failures += 1
                continue
            print(json.dumps(summary.as_dict(), indent=2))
    finally:
        await close_pool()
    return 1 if failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract financial facts from filings into the metric store."
    )
    parser.add_argument("files", nargs="+", help="Filing files (HTML for now).")
    parser.add_argument("--entity", required=True, help="Entity id (e.g. ticker).")
    parser.add_argument("--name", default=None, help="Entity display name.")
    parser.add_argument(
        "--filed", default=None,
        help="Filing date YYYY-MM-DD (drives restatement precedence).",
    )
    parser.add_argument(
        "--fye-month", default=12, type=int, choices=range(1, 13),
        help="Entity fiscal-year-end month (12 = calendar; Apple = 9).",
    )
    args = parser.parse_args()
    filed = datetime.strptime(args.filed, "%Y-%m-%d").date() if args.filed else None

    configure_logging(get_settings().log_level)
    raise SystemExit(
        asyncio.run(_run(args.files, args.entity, args.name, filed, args.fye_month))
    )


if __name__ == "__main__":
    main()
