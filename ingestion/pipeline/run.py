"""Ingestion CLI: initial backfill and manual re-index.

Examples:
  python -m ingestion.pipeline.run --source ./sample_docs
  python -m ingestion.pipeline.run            # uses DOC_SOURCE / settings

Idempotent: re-running only re-embeds changed chunks and prunes deleted docs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging

from app.config import get_settings
from app.db.pool import close_pool
from app.embeddings import build_embedding_provider
from app.logging import configure_logging
from app.vectorstore import build_vector_store

from ingestion.pipeline.indexer import Indexer
from ingestion.pipeline.source import LocalFolderSource, build_source

logger = logging.getLogger("rag.ingest")


async def _run(source_override: str | None) -> int:
    settings = get_settings()
    source = (
        LocalFolderSource(source_override) if source_override else build_source()
    )
    embedder = build_embedding_provider(settings)
    store = build_vector_store()

    indexer = Indexer(source, embedder, store, settings)
    try:
        summary = await indexer.run()
    finally:
        await close_pool()

    logger.info("ingest complete", extra={"extra": summary.as_dict()})
    print(json.dumps(summary.as_dict(), indent=2, default=str))
    return 1 if summary.failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into the RAG index.")
    parser.add_argument(
        "--source",
        help="Local folder to ingest (overrides DOC_SOURCE; forces local mode).",
        default=None,
    )
    args = parser.parse_args()

    configure_logging(get_settings().log_level)
    exit_code = asyncio.run(_run(args.source))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
