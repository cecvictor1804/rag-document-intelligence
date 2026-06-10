"""Data transfer objects shared across ingestion, retrieval, and generation.

These are plain dataclasses (not Pydantic) so they're cheap to construct in
tight ingestion loops and trivially usable from both halves of the system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


@dataclass(slots=True)
class DocRef:
    """A pointer to a source document, before its content is fetched."""

    doc_id: str  # stable identity (e.g. relative path or S3 key)
    source_url: str  # where a human can open the original
    filetype: str  # "pdf" | "docx" | "html" | "md" | "txt"
    last_modified: datetime | None = None


@dataclass(slots=True)
class RawDocument:
    """A fetched document: extracted text plus identifying metadata."""

    ref: DocRef
    title: str
    text: str
    # Per-document access control. Empty list == world-readable (flat mode).
    acl: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Chunk:
    """A unit of indexed text with its embedding and provenance metadata."""

    doc_id: str
    content_hash: str  # sha256 of the chunk text — the upsert key with doc_id
    ordinal: int  # position of the chunk within the document
    text: str
    title: str
    section: str | None = None
    source_url: str = ""
    last_modified: datetime | None = None
    embedding: list[float] | None = None
    acl: list[str] = field(default_factory=list)
    chunk_id: int | None = None  # DB id, populated on retrieval (for feedback)


@dataclass(slots=True)
class RetrievedChunk:
    """A chunk returned by retrieval, carrying its score and origin."""

    chunk: Chunk
    score: float
    source: str  # "dense" | "lexical" | "fused"


@dataclass(slots=True)
class RerankResult:
    """A chunk after reranking, with the reranker's relevance score."""

    chunk: Chunk
    rerank_score: float


@dataclass(slots=True)
class Citation:
    """A source reference attached to a generated answer."""

    n: int  # the [n] marker used inline in the answer
    doc_id: str
    title: str
    section: str | None
    source_url: str
    snippet: str


class AnswerEventType(StrEnum):
    TOKEN = "token"
    CITATIONS = "citations"
    META = "meta"  # routing decision, model used, etc.
    METRICS = "metrics"  # deterministic figures resolved by the planner
    SERIES = "series"  # multi-period series for charting
    VERIFICATION = "verification"  # post-stream number check (flags, not edits)
    DONE = "done"
    ERROR = "error"


@dataclass(slots=True)
class AnswerEvent:
    """A single streamed event from the generation layer to the client."""

    type: AnswerEventType
    data: Any  # str for TOKEN; list[Citation] for CITATIONS; dict for META/DONE


@dataclass(slots=True)
class Turn:
    """One prior turn of conversation, for multi-turn context."""

    role: str  # "user" | "assistant"
    content: str


@dataclass(slots=True)
class IngestSummary:
    """Returned by the indexer after a run; logged and surfaced to operators."""

    docs_seen: int = 0
    changed: int = 0
    skipped: int = 0
    chunks_upserted: int = 0
    chunks_deleted: int = 0
    docs_deleted: int = 0
    failures: list[tuple[str, str]] = field(default_factory=list)  # (doc_id, error)

    def as_dict(self) -> dict[str, Any]:
        return {
            "docs_seen": self.docs_seen,
            "changed": self.changed,
            "skipped": self.skipped,
            "chunks_upserted": self.chunks_upserted,
            "chunks_deleted": self.chunks_deleted,
            "docs_deleted": self.docs_deleted,
            "failures": self.failures,
        }
