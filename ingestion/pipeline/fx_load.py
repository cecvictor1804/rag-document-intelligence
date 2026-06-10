"""Load ECB reference FX rates into the fx_rates table.

Examples:
  python -m ingestion.pipeline.fx_load          # last ~90 days (default feed)
  make fx-load

The ECB publishes EUR-based reference rates daily (free, no key). Cross rates
(e.g. USD→GBP) are derived via EUR at query time. Conversions in answers are
always annotated with the applied rate + its as-of date.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx
from app.config import get_settings
from app.db.pool import close_pool
from app.finance.fx import parse_ecb_rates
from app.finance.store import PgMetricStore
from app.logging import configure_logging

logger = logging.getLogger("rag.fx")

ECB_90D_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"

Fetch = Callable[[str], Awaitable[bytes]]


async def _http_fetch(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content


async def load_rates(store: PgMetricStore, fetch: Fetch = _http_fetch) -> int:
    rows = parse_ecb_rates(await fetch(ECB_90D_URL))
    n = await store.upsert_fx_rates(rows)
    logger.info("fx: upserted %d rate rows", n)
    return n


async def _run() -> int:
    try:
        n = await load_rates(PgMetricStore())
    finally:
        await close_pool()
    print(f"Loaded {n} FX rate rows (ECB, EUR-based).")
    return 0 if n else 1


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    configure_logging(get_settings().log_level)
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
