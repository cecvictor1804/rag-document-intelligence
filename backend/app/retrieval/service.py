"""Retrieval orchestration: embed -> dense + lexical -> fuse -> rerank.

Dense and lexical searches run concurrently. Their results are fused with RRF,
truncated to `fuse_top_k`, then reranked down to `rerank_top_k`. The reranked
list is what generation grounds its answer on.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from app.config import Settings
from app.core.interfaces import EmbeddingProvider, Reranker, VectorStore
from app.core.models import RerankResult
from app.retrieval.fusion import rrf_fuse


class RetrievalService:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        store: VectorStore,
        reranker: Reranker,
        settings: Settings,
    ) -> None:
        self.embedder = embedder
        self.store = store
        self.reranker = reranker
        self.settings = settings

    async def retrieve(
        self, query: str, acl_filter: Sequence[str] | None = None
    ) -> list[RerankResult]:
        s = self.settings
        qvec = await self.embedder.embed_query(query)
        dense, lexical = await asyncio.gather(
            self.store.dense_search(qvec, s.dense_top_k, acl_filter),
            self.store.lexical_search(query, s.lexical_top_k, acl_filter),
        )
        fused = rrf_fuse(dense, lexical, s.rrf_k)[: s.fuse_top_k]
        if not fused:
            return []
        return await self.reranker.rerank(query, fused, s.rerank_top_k)
