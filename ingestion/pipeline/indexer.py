"""The idempotent indexer.

For each source document:
  fetch -> clean -> doc sha256.
  If the doc hash is unchanged, skip (no work, no embeddings spent).
  Otherwise: chunk -> per-chunk sha256 -> embed ONLY chunks not already stored
  -> upsert -> delete_missing (drop stale chunks whose text changed/disappeared).

After processing every document, any doc_id present in the store but absent from
the source is removed (delete_documents -> cascade). Re-running converges to the
exact source state and never duplicates.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.config import Settings
from app.core.interfaces import DocumentSource, EmbeddingProvider, VectorStore
from app.core.models import Chunk, DocRef, IngestSummary

from ingestion.pipeline.chunk import chunk_text
from ingestion.pipeline.clean import clean_text
from ingestion.pipeline.hashing import sha256_text

logger = logging.getLogger("rag.indexer")


class Indexer:
    def __init__(
        self,
        source: DocumentSource,
        embedder: EmbeddingProvider,
        store: VectorStore,
        settings: Settings,
    ) -> None:
        self.source = source
        self.embedder = embedder
        self.store = store
        self.settings = settings

    async def _index_document(self, ref: DocRef, summary: IngestSummary) -> None:
        raw = await self.source.fetch(ref)
        cleaned = clean_text(raw.text)
        doc_hash = sha256_text(cleaned)

        existing_hash = await self.store.get_document_hash(ref.doc_id)
        if existing_hash == doc_hash:
            summary.skipped += 1
            logger.info("skip unchanged", extra={"extra": {"doc_id": ref.doc_id}})
            return

        text_chunks = chunk_text(
            cleaned,
            chunk_tokens=self.settings.chunk_tokens,
            overlap_tokens=self.settings.chunk_overlap_tokens,
        )
        if not text_chunks:
            logger.warning("no chunks produced", extra={"extra": {"doc_id": ref.doc_id}})
            # Still record the document so deletion detection treats it as seen.
            await self.store.upsert_document(ref, raw.title, doc_hash, raw.acl)
            summary.changed += 1
            return

        # Build Chunk objects with content hashes; embed all (text changed).
        chunks: list[Chunk] = []
        for tc in text_chunks:
            chunks.append(
                Chunk(
                    doc_id=ref.doc_id,
                    content_hash=sha256_text(tc.text),
                    ordinal=tc.ordinal,
                    text=tc.text,
                    title=raw.title,
                    section=tc.section,
                    source_url=ref.source_url,
                    last_modified=ref.last_modified,
                    acl=raw.acl,
                )
            )

        embeddings = await self.embedder.embed_documents([c.text for c in chunks])
        for chunk, emb in zip(chunks, embeddings, strict=True):
            chunk.embedding = emb

        await self.store.upsert_document(ref, raw.title, doc_hash, raw.acl)
        upserted = await self.store.upsert_chunks(chunks)
        deleted = await self.store.delete_missing(
            ref.doc_id, [c.content_hash for c in chunks]
        )

        summary.changed += 1
        summary.chunks_upserted += upserted
        summary.chunks_deleted += deleted
        logger.info(
            "indexed",
            extra={
                "extra": {
                    "doc_id": ref.doc_id,
                    "chunks": upserted,
                    "pruned": deleted,
                }
            },
        )

    async def run(self, restrict_doc_ids: Sequence[str] | None = None) -> IngestSummary:
        """Index the corpus. `restrict_doc_ids`, when given, limits processing to
        specific doc_ids (used by the event-driven worker for changed keys) and
        disables corpus-wide deletion detection."""
        summary = IngestSummary()
        refs = list(await self.source.list_documents())
        if restrict_doc_ids is not None:
            wanted = set(restrict_doc_ids)
            refs = [r for r in refs if r.doc_id in wanted]

        summary.docs_seen = len(refs)
        seen_ids: set[str] = set()
        for ref in refs:
            seen_ids.add(ref.doc_id)
            try:
                await self._index_document(ref, summary)
            except Exception as exc:  # noqa: BLE001 — collect per-doc failures
                logger.exception("failed to index %s", ref.doc_id)
                summary.failures.append((ref.doc_id, str(exc)))

        # Corpus-wide deletion detection only on a full run.
        if restrict_doc_ids is None:
            stored = await self.store.list_document_ids()
            removed = list(stored - seen_ids)
            if removed:
                summary.docs_deleted = await self.store.delete_documents(removed)
                logger.info("removed deleted docs", extra={"extra": {"count": len(removed)}})

        return summary
