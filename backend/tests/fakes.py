"""Shared in-memory fakes + builders for the Phase 2 engine tests (no DB, no API).

Importable as `from fakes import ...` (pytest prepends the test dir to sys.path),
mirroring the fakes style in ingestion/tests/test_indexer.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from app.config import Settings
from app.core.models import (
    AnswerEvent,
    AnswerEventType,
    Chunk,
    RerankResult,
    RetrievedChunk,
    Turn,
)


def settings(**over) -> Settings:
    """Settings with explicit defaults so tests don't depend on a local .env."""
    base = dict(
        dense_top_k=50,
        lexical_top_k=50,
        rrf_k=60,
        fuse_top_k=40,
        rerank_top_k=8,
        min_rerank_score=0.3,
        router_enabled=True,
        router_model_cheap="claude-haiku-4-5",
        router_model_mid="claude-sonnet-4-6",
        router_model_strong="claude-opus-4-8",
        router_high_confidence=0.65,
        router_low_confidence=0.45,
        router_long_context_tokens=150_000,
        router_default_effort="medium",
    )
    base.update(over)
    return Settings(**base)


def make_chunk(
    doc_id: str = "d.txt",
    content_hash: str = "h",
    text: str = "some text",
    title: str = "Doc",
    section: str | None = None,
    source_url: str = "file:///d.txt",
) -> Chunk:
    return Chunk(
        doc_id=doc_id,
        content_hash=content_hash,
        ordinal=0,
        text=text,
        title=title,
        section=section,
        source_url=source_url,
    )


def rc(chunk: Chunk, score: float = 1.0, source: str = "dense") -> RetrievedChunk:
    return RetrievedChunk(chunk=chunk, score=score, source=source)


def rr(chunk: Chunk, score: float = 1.0) -> RerankResult:
    return RerankResult(chunk=chunk, rerank_score=score)


class FakeEmbedder:
    name = "fake"
    dim = 4

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


class FakeStore:
    """Returns preconfigured dense/lexical results, ignoring the actual query."""

    def __init__(
        self, dense: Sequence[RetrievedChunk], lexical: Sequence[RetrievedChunk]
    ) -> None:
        self._dense = list(dense)
        self._lexical = list(lexical)
        self.dense_k: int | None = None
        self.lexical_k: int | None = None

    async def dense_search(self, embedding, top_k, acl_filter=None):
        self.dense_k = top_k
        return self._dense[:top_k]

    async def lexical_search(self, query, top_k, acl_filter=None):
        self.lexical_k = top_k
        return self._lexical[:top_k]


class FakeReranker:
    """Identity reranker: preserve fused order, assign descending scores, top_k cut."""

    name = "fake"

    def __init__(self, results: Sequence[RerankResult] | None = None) -> None:
        self._results = list(results) if results is not None else None

    async def rerank(self, query, candidates, top_k):
        if self._results is not None:
            return self._results[:top_k]
        return [
            RerankResult(chunk=c.chunk, rerank_score=1.0 - 0.01 * i)
            for i, c in enumerate(candidates[:top_k])
        ]


class FakeRetrieval:
    """Stands in for RetrievalService; returns a preset reranked list."""

    def __init__(self, results: Sequence[RerankResult]) -> None:
        self._results = list(results)

    async def retrieve(self, query, acl_filter=None) -> list[RerankResult]:
        return list(self._results)


class FakeLLM:
    """Records calls; yields a preset event sequence (default: token + done)."""

    def __init__(self, events: Sequence[AnswerEvent] | None = None) -> None:
        self.calls = 0
        self._events = list(events) if events is not None else [
            AnswerEvent(AnswerEventType.TOKEN, "answer [1]"),
            AnswerEvent(AnswerEventType.DONE, {"model": "x", "usage": {}}),
        ]

    async def stream_grounded_answer(
        self, query, context, model, effort, history: Sequence[Turn] = ()
    ) -> AsyncIterator[AnswerEvent]:
        self.calls += 1
        self.last = {"model": model, "effort": effort, "history": list(history)}
        for ev in self._events:
            yield ev
