"""Event-driven ingestion worker (steady-state path in production).

Long-polls an SQS queue fed by S3 `ObjectCreated:*` / `ObjectRemoved:*`
notifications, and incrementally processes just the affected keys:
  - created/updated keys -> Indexer.run(restrict_doc_ids=[...])  (narrative)
  - created keys shaped `<ENTITY>/<file>` additionally run the financial
    extraction path (entity = the top-level folder), concurrently under a
    semaphore (WORKER_CONCURRENCY)
  - removed keys -> VectorStore.delete_documents([...])

Run with: python -m ingestion.pipeline.worker
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from urllib.parse import unquote_plus

from app.config import get_settings
from app.core.models import DocRef
from app.db.pool import close_pool
from app.embeddings import build_embedding_provider
from app.logging import configure_logging
from app.vectorstore import build_vector_store

from ingestion.pipeline.financial import FinancialIngestor
from ingestion.pipeline.indexer import Indexer
from ingestion.pipeline.loaders import SUPPORTED_EXTENSIONS, filetype_for
from ingestion.pipeline.source import build_source

logger = logging.getLogger("rag.worker")

FetchBytes = Callable[[str], Awaitable[bytes]]


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


def _entity_for_key(key: str) -> str | None:
    """S3 key convention `<ENTITY>/<file>`: the top-level folder names the
    entity for financial extraction; keys without a folder skip that path."""
    head, sep, tail = key.partition("/")
    if not sep or not tail or "/" in tail or not head:
        return None
    return head


def _filetype_of(key: str) -> str:
    ext = filetype_for(key)
    return "html" if ext in {"htm", "html"} else ext


async def handle_financial(
    ingestor: FinancialIngestor,
    fetch_bytes: FetchBytes,
    created: set[str],
    concurrency: int = 4,
) -> int:
    """Run financial extraction for entity-foldered keys, concurrently."""
    keys = [(k, e) for k in sorted(created) if (e := _entity_for_key(k))]
    if not keys:
        return 0
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(key: str, entity: str) -> bool:
        async with semaphore:
            try:
                content = await fetch_bytes(key)
                ref = DocRef(
                    doc_id=key, source_url=f"s3://{key}", filetype=_filetype_of(key)
                )
                summary = await ingestor.ingest(ref, content, entity)
                logger.info("worker financial", extra={"extra": summary.as_dict()})
                return True
            except Exception:  # noqa: BLE001 — one bad doc must not stop the rest
                logger.exception("financial ingest failed for %s", key)
                return False

    results = await asyncio.gather(*(one(k, e) for k, e in keys))
    return sum(results)


async def _handle(
    indexer: Indexer,
    store,
    created: set[str],
    removed: set[str],
    financial: FinancialIngestor | None = None,
    fetch_bytes: FetchBytes | None = None,
    concurrency: int = 4,
) -> None:
    if created:
        summary = await indexer.run(restrict_doc_ids=list(created))
        logger.info("worker indexed", extra={"extra": summary.as_dict()})
        if financial is not None and fetch_bytes is not None:
            await handle_financial(financial, fetch_bytes, created, concurrency)
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

    # Financial path: parse tables → facts for keys shaped <ENTITY>/<file>.
    from app.extraction import build_financial_parser
    from app.finance.store import PgMetricStore

    financial = FinancialIngestor(build_financial_parser(settings), PgMetricStore())
    s3 = boto3.client("s3", region_name=settings.aws_region)

    async def fetch_bytes(key: str) -> bytes:
        obj = await asyncio.to_thread(
            s3.get_object, Bucket=settings.s3_bucket, Key=key
        )
        return obj["Body"].read()

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
                    await _handle(
                        indexer, store, created, removed,
                        financial=financial, fetch_bytes=fetch_bytes,
                        concurrency=settings.worker_concurrency,
                    )
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
