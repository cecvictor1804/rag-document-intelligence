"""Voyage reranker.

Takes the fused candidate list and re-scores it with a cross-encoder, which is
far more accurate than the first-stage dense/lexical scores. Wrapped with the
resilience helper like every other external call.
"""

from __future__ import annotations

from collections.abc import Sequence

import voyageai

from app.core.models import RerankResult, RetrievedChunk
from app.core.resilience import with_retry


class VoyageReranker:
    def __init__(self, api_key: str, model: str = "rerank-2") -> None:
        self.name = f"voyage:{model}"
        self._model = model
        self._client = voyageai.AsyncClient(api_key=api_key or None)

    async def rerank(
        self, query: str, candidates: Sequence[RetrievedChunk], top_k: int
    ) -> list[RerankResult]:
        if not candidates:
            return []
        documents = [c.chunk.text for c in candidates]

        async def _call():
            return await self._client.rerank(
                query, documents, model=self._model, top_k=top_k
            )

        resp = await with_retry(_call, what="voyage.rerank")
        # Each result carries the index into `documents` and a relevance score;
        # map back to the originating chunk.
        return [
            RerankResult(
                chunk=candidates[r.index].chunk,
                rerank_score=float(r.relevance_score),
            )
            for r in resp.results
        ]
