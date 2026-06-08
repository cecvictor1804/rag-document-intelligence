"""Event-driven ingestion worker (steady-state path in production).

Long-polls an SQS queue fed by S3 `ObjectCreated:*` / `ObjectRemoved:*`
notifications, and incrementally re-indexes just the affected keys:
  - created/updated keys  -> Indexer.run(restrict_doc_ids=[...])
  - removed keys          -> VectorStore.delete_documents([...])

Run with: python -m ingestion.pipeline.worker
"""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import unquote_plus

from app.config import get_settings
from app.db.pool import close_pool
from app.embeddings import build_embedding_provider
from app.logging import configure_logging
from app.vectorstore import build_vector_store

from ingestion.pipeline.indexer import Indexer
from ingestion.pipeline.loaders import SUPPORTED_EXTENSIONS, filetype_for
from ingestion.pipeline.source import build_source

logger = logging.getLogger("rag.worker")


def _parse_records(body: str) -> tuple[set[str], set[str]]:
    """Return (created_keys, removed_keys) from an S3-notification SQS message."""
    created: set[str] = set()
    removed: set[str] = set()
    msg = json.loads(body)
    for rec in msg.get("Records", []):
        event = rec.get("eventName", "")
        key = unquote_plus(rec.get("s3", {}).get("object", {}).get("key", ""))
        if not key or f".{filetype_for(key)}" not in SUPPORTED_EXTENSIONS:
            continue
        if event.startswith("ObjectCreated"):
            created.add(key)
        elif event.startswith("ObjectRemoved"):
            removed.add(key)
    return created, removed


async def _handle(indexer: Indexer, store, created: set[str], removed: set[str]) -> None:
    if created:
        summary = await indexer.run(restrict_doc_ids=list(created))
        logger.info("worker indexed", extra={"extra": summary.as_dict()})
    if removed:
        n = await store.delete_documents(list(removed))
        logger.info("worker removed", extra={"extra": {"docs_deleted": n}})


async def _poll_loop() -> None:
    import boto3

    settings = get_settings()
    sqs = boto3.client("sqs", region_name=settings.aws_region)
    queue_url = settings.ingest_sqs_queue_url
    if not queue_url:
        raise SystemExit("INGEST_SQS_QUEUE_URL is not set")

    source = build_source()
    embedder = build_embedding_provider(settings)
    store = build_vector_store()
    indexer = Indexer(source, embedder, store, settings)

    logger.info("worker started", extra={"extra": {"queue": queue_url}})
    try:
        while True:
            resp = await asyncio.to_thread(
                sqs.receive_message,
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,
            )
            for m in resp.get("Messages", []):
                try:
                    created, removed = _parse_records(m["Body"])
                    await _handle(indexer, store, created, removed)
                    await asyncio.to_thread(
                        sqs.delete_message,
                        QueueUrl=queue_url,
                        ReceiptHandle=m["ReceiptHandle"],
                    )
                except Exception:  # noqa: BLE001 — leave message for redelivery
                    logger.exception("failed handling SQS message")
    finally:
        await close_pool()


def main() -> None:
    configure_logging(get_settings().log_level)
    asyncio.run(_poll_loop())


if __name__ == "__main__":
    main()
