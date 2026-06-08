"""Reciprocal Rank Fusion of the dense and lexical result lists.

RRF combines two ranked lists without needing their scores to be comparable: a
chunk's fused score is the sum of ``1 / (rrf_k + rank)`` over the lists it
appears in (rank is 0-based). Chunks found by *both* dense and lexical search
rise to the top. Pure and synchronous — fully unit-testable without a DB.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.models import RetrievedChunk


def _key(rc: RetrievedChunk) -> tuple[str, str]:
    return (rc.chunk.doc_id, rc.chunk.content_hash)


def rrf_fuse(
    dense: Sequence[RetrievedChunk],
    lexical: Sequence[RetrievedChunk],
    rrf_k: int,
) -> list[RetrievedChunk]:
    """Fuse two ranked lists into one, sorted by RRF score (desc)."""
    scores: dict[tuple[str, str], float] = {}
    chunks: dict[tuple[str, str], RetrievedChunk] = {}

    for ranked in (dense, lexical):
        for rank, rc in enumerate(ranked):
            k = _key(rc)
            scores[k] = scores.get(k, 0.0) + 1.0 / (rrf_k + rank)
            # Keep the first RetrievedChunk seen for the payload; mark it fused.
            chunks.setdefault(k, rc)

    fused = [
        RetrievedChunk(chunk=chunks[k].chunk, score=score, source="fused")
        for k, score in scores.items()
    ]
    fused.sort(key=lambda rc: rc.score, reverse=True)
    return fused
