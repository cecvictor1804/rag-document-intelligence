"""OpenAI embedding provider (alternate). Requires the `openai` optional extra.

Demonstrates the swappable seam: same Protocol, different vendor. `text-embedding-3-large`
defaults to 3072 dims but supports the `dimensions` parameter to match the
configured EMBEDDING_DIM (and the migration's vector size).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.resilience import with_retry

_BATCH = 256


class OpenAIEmbeddingProvider:
    def __init__(
        self, api_key: str, model: str = "text-embedding-3-large", dim: int = 1024
    ) -> None:
        from openai import AsyncOpenAI

        self.name = f"openai:{model}"
        self.dim = dim
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key or None)

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for start in range(0, len(texts), _BATCH):
            batch = list(texts[start : start + _BATCH])

            async def _call(batch: list[str] = batch) -> list[list[float]]:
                resp = await self._client.embeddings.create(
                    input=batch, model=self._model, dimensions=self.dim
                )
                return [d.embedding for d in resp.data]

            out.extend(await with_retry(_call, what="openai.embed"))
        return out

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        result = await self._embed([text])
        return result[0]
