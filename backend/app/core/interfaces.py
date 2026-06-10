"""Swappable provider Protocols — the seams that keep the system pluggable.

Concrete implementations (Voyage, OpenAI, pgvector, Anthropic, ...) are selected
at startup in `app.deps` from configuration. Code throughout the system depends
only on these Protocols, never on a concrete vendor, so a provider or the vector
store can be swapped without touching retrieval or generation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol, runtime_checkable

from app.core.finance import (
    Basis,
    FinancialDocMeta,
    FinancialFact,
    FiscalPeriod,
    ParsedFinancialDoc,
)
from app.core.models import (
    AnswerEvent,
    Chunk,
    DocRef,
    RawDocument,
    RerankResult,
    RetrievedChunk,
    Turn,
)


@runtime_checkable
class DocumentSource(Protocol):
    """Where documents come from. LocalFolderSource (dev) and S3Source (prod)
    implement this so the ingestion pipeline is source-agnostic."""

    async def list_documents(self) -> Sequence[DocRef]: ...

    async def fetch(self, ref: DocRef) -> RawDocument: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    dim: int

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


@runtime_checkable
class Reranker(Protocol):
    name: str

    async def rerank(
        self, query: str, candidates: Sequence[RetrievedChunk], top_k: int
    ) -> list[RerankResult]: ...


@runtime_checkable
class VectorStore(Protocol):
    """Dense + lexical retrieval and idempotent writes. pgvector is the v1
    implementation; the Protocol lets a managed DB be swapped in later."""

    async def upsert_chunks(self, chunks: Sequence[Chunk]) -> int: ...

    async def dense_search(
        self,
        embedding: Sequence[float],
        top_k: int,
        acl_filter: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]: ...

    async def lexical_search(
        self,
        query: str,
        top_k: int,
        acl_filter: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]: ...

    async def get_document_hash(self, doc_id: str) -> str | None: ...

    async def upsert_document(
        self, ref: DocRef, title: str, content_hash: str, acl: Sequence[str]
    ) -> None: ...

    async def list_document_ids(self) -> set[str]: ...

    async def delete_missing(
        self, doc_id: str, keep_chunk_hashes: Sequence[str]
    ) -> int:
        """Remove chunks of `doc_id` whose hash is not in `keep_chunk_hashes`
        (i.e. chunks that changed or disappeared on re-index)."""
        ...

    async def delete_documents(self, doc_ids: Sequence[str]) -> int:
        """Remove documents (and their chunks, via cascade) no longer in source."""
        ...


@runtime_checkable
class FinancialParser(Protocol):
    """Turns a raw document (incl. scanned PDFs) into narrative text + structured
    tables with cell positions. The commercial extraction vendor lives behind
    this seam so it can be swapped (or faked in tests) without touching the
    fact mapper or anything downstream."""

    name: str

    async def parse(self, ref: DocRef, content: bytes) -> ParsedFinancialDoc: ...


@runtime_checkable
class MetricStore(Protocol):
    """Reads/writes for the canonical financial fact store. The Postgres
    implementation resolves conflicts via the authoritative-facts view
    (authority rank, then filing recency)."""

    async def upsert_entity(
        self, entity_id: str, name: str, ticker: str | None = None,
        cik: str | None = None,
    ) -> None: ...

    async def upsert_document(self, meta: FinancialDocMeta) -> None: ...

    async def upsert_facts(self, facts: Sequence[FinancialFact]) -> int: ...

    async def get_fact(
        self,
        entity_id: str,
        line_item: str,
        period: FiscalPeriod,
        basis: Basis = Basis.GAAP,
        segment: str | None = None,
    ) -> FinancialFact | None:
        """The authoritative value of one canonical line item for one period."""
        ...

    async def get_series(
        self,
        entity_id: str,
        line_item: str,
        basis: Basis = Basis.GAAP,
        segment: str | None = None,
        limit: int = 12,
    ) -> list[FinancialFact]:
        """Authoritative period-aligned series, most recent first."""
        ...


@runtime_checkable
class QueryPlanner(Protocol):
    """Maps a chat question to the verified figures it needs (or None for a
    pure-narrative answer). Implemented by finance.planner.LLMQueryPlanner."""

    async def plan(self, query: str) -> Any:  # finance.planner.QueryPlan | None
        ...


@runtime_checkable
class LLMClient(Protocol):
    """Streams a grounded, cited answer from retrieved context."""

    def stream_grounded_answer(
        self,
        query: str,
        context: Sequence[RerankResult],
        model: str,
        effort: str,
        history: Sequence[Turn] = (),
    ) -> AsyncIterator[AnswerEvent]:
        """An async generator — call without `await`, then `async for` its events."""
        ...
