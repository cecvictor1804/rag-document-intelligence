"""Indexer idempotency and deletion detection, using in-memory fakes (no DB,
no network). This is the unit-level mirror of the Phase 1 demo:
  - first run indexes everything
  - re-run with no changes skips everything
  - editing a doc re-embeds only that doc and prunes its stale chunks
  - removing a doc from source deletes it from the store
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from app.config import Settings
from app.core.models import Chunk, DocRef, RawDocument

from ingestion.pipeline.indexer import Indexer


class FakeSource:
    """In-memory document source. Mutate `docs` between runs to simulate edits."""

    def __init__(self, docs: dict[str, str]) -> None:
        self.docs = docs  # doc_id -> text

    async def list_documents(self) -> Sequence[DocRef]:
        return [
            DocRef(
                doc_id=doc_id,
                source_url=f"file:///{doc_id}",
                filetype="txt",
                last_modified=datetime(2026, 1, 1, tzinfo=UTC),
            )
            for doc_id in self.docs
        ]

    async def fetch(self, ref: DocRef) -> RawDocument:
        return RawDocument(ref=ref, title=ref.doc_id, text=self.docs[ref.doc_id], acl=[])


class FakeEmbedder:
    name = "fake"
    dim = 4

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(len(t)), 1.0, 0.0, 0.0] for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [float(len(text)), 1.0, 0.0, 0.0]


class FakeStore:
    """Mirrors PgVectorStore write/idempotency semantics in memory."""

    def __init__(self) -> None:
        self.doc_hashes: dict[str, str] = {}
        self.chunks: dict[str, dict[str, Chunk]] = {}  # doc_id -> {hash: chunk}

    async def get_document_hash(self, doc_id: str) -> str | None:
        return self.doc_hashes.get(doc_id)

    async def upsert_document(self, ref, title, content_hash, acl) -> None:
        self.doc_hashes[ref.doc_id] = content_hash
        self.chunks.setdefault(ref.doc_id, {})

    async def list_document_ids(self) -> set[str]:
        return set(self.doc_hashes)

    async def upsert_chunks(self, chunks: Sequence[Chunk]) -> int:
        for c in chunks:
            assert c.embedding is not None, "chunks must be embedded before upsert"
            self.chunks.setdefault(c.doc_id, {})[c.content_hash] = c
        return len(chunks)

    async def delete_missing(self, doc_id: str, keep_chunk_hashes: Sequence[str]) -> int:
        keep = set(keep_chunk_hashes)
        existing = self.chunks.get(doc_id, {})
        stale = [h for h in existing if h not in keep]
        for h in stale:
            del existing[h]
        return len(stale)

    async def delete_documents(self, doc_ids: Sequence[str]) -> int:
        n = 0
        for doc_id in doc_ids:
            if doc_id in self.doc_hashes:
                del self.doc_hashes[doc_id]
                self.chunks.pop(doc_id, None)
                n += 1
        return n

    def total_chunks(self) -> int:
        return sum(len(v) for v in self.chunks.values())


def _settings() -> Settings:
    return Settings(chunk_tokens=600, chunk_overlap_ratio=0.15)


@pytest.mark.asyncio
async def test_first_run_indexes_everything():
    source = FakeSource({"a.txt": "Alpha content here.", "b.txt": "Bravo content."})
    store = FakeStore()
    indexer = Indexer(source, FakeEmbedder(), store, _settings())

    summary = await indexer.run()

    assert summary.docs_seen == 2
    assert summary.changed == 2
    assert summary.skipped == 0
    assert store.total_chunks() == 2


@pytest.mark.asyncio
async def test_rerun_unchanged_skips_all():
    source = FakeSource({"a.txt": "Alpha content here.", "b.txt": "Bravo content."})
    store = FakeStore()
    indexer = Indexer(source, FakeEmbedder(), store, _settings())

    await indexer.run()
    summary = await indexer.run()

    assert summary.skipped == 2
    assert summary.changed == 0
    assert summary.chunks_upserted == 0


@pytest.mark.asyncio
async def test_editing_a_doc_reindexes_and_prunes_stale_chunks():
    source = FakeSource({"a.txt": "Original content for doc A."})
    store = FakeStore()
    indexer = Indexer(source, FakeEmbedder(), store, _settings())

    await indexer.run()
    assert store.total_chunks() == 1

    source.docs["a.txt"] = "Completely different content now."
    summary = await indexer.run()

    assert summary.changed == 1
    assert summary.chunks_deleted == 1  # old single chunk pruned
    assert store.total_chunks() == 1  # replaced, not duplicated


@pytest.mark.asyncio
async def test_removing_a_doc_deletes_it():
    source = FakeSource({"a.txt": "Doc A.", "b.txt": "Doc B."})
    store = FakeStore()
    indexer = Indexer(source, FakeEmbedder(), store, _settings())

    await indexer.run()
    del source.docs["b.txt"]
    summary = await indexer.run()

    assert summary.docs_deleted == 1
    assert await store.list_document_ids() == {"a.txt"}
