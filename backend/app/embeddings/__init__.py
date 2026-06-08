"""Embedding providers (Voyage default, OpenAI alternate) behind a Protocol."""

from __future__ import annotations

from app.config import Settings
from app.core.interfaces import EmbeddingProvider


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Select the configured embedding provider."""
    if settings.embedding_provider == "openai":
        from app.embeddings.openai import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
        )

    from app.embeddings.voyage import VoyageEmbeddingProvider

    return VoyageEmbeddingProvider(
        api_key=settings.voyage_api_key,
        model=settings.embedding_model,
        dim=settings.embedding_dim,
    )
