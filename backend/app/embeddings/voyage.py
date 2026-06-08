"""Voyage embedding provider (default).

Uses Voyage's `input_type` distinction ("document" vs "query") which improves
retrieval quality. Calls are batched and wrapped with the resilience helper.
"""

from __future__ import annotations

from collections.abc import Sequence

import voyageai

from app.core.resilience import with_retry

_BATCH = 128  # Voyage accepts up to 128 inputs per request


class VoyageEmbeddingProvider:
    def __init__(self, api_key: str, model: str = "voyage-3", dim: int = 1024) -> None:
        self.name = f"voyage:{model}"
        self.dim = dim
        self._model = model
        self._client = voyageai.AsyncClient(api_key=api_key or None)

    async def _embed(self, texts: Sequence[str], input_type: str) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            batch = list(texts[start : start + _BATCH])

            async def _call(batch: list[str] = batch) -> list[list[float]]:
                resp = await self._client.embed(
                    batch, model=self._model, input_type=input_type
                )
                return resp.embeddings

            out.extend(await with_retry(_call, what="voyage.embed"))
        return out

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embed(texts, input_type="document")

    async def embed_query(self, text: str) -> list[float]:
        result = await self._embed([text], input_type="query")
        return result[0]
