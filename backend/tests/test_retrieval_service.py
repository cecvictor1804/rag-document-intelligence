"""RetrievalService: embed -> dense+lexical -> RRF fuse -> rerank (top_k honored)."""

from __future__ import annotations

import pytest
from app.retrieval.service import RetrievalService
from fakes import FakeEmbedder, FakeReranker, FakeStore, make_chunk, rc, settings

A = make_chunk(doc_id="a.txt", content_hash="a")
B = make_chunk(doc_id="b.txt", content_hash="b")
C = make_chunk(doc_id="c.txt", content_hash="c")


@pytest.mark.asyncio
async def test_fuses_then_reranks_and_truncates():
    store = FakeStore(
        dense=[rc(A, source="dense"), rc(B, source="dense")],
        lexical=[rc(B, source="lexical"), rc(C, source="lexical")],
    )
    svc = RetrievalService(FakeEmbedder(), store, FakeReranker(), settings(rerank_top_k=2))

    out = await svc.retrieve("q")

    # B (in both lists) ranks first after fusion; identity reranker keeps order,
    # rerank_top_k=2 truncates to two results.
    assert [r.chunk.doc_id for r in out] == ["b.txt", "a.txt"]
    assert store.dense_k == 50 and store.lexical_k == 50  # from settings top-ks


@pytest.mark.asyncio
async def test_empty_when_nothing_retrieved():
    store = FakeStore(dense=[], lexical=[])
    svc = RetrievalService(FakeEmbedder(), store, FakeReranker(), settings())
    assert await svc.retrieve("q") == []
