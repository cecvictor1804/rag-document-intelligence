"""Rerankers behind the `Reranker` Protocol (Voyage is the v1 implementation)."""

from __future__ import annotations

from app.config import Settings
from app.core.interfaces import Reranker


def build_reranker(settings: Settings) -> Reranker:
    """Select the configured reranker."""
    # Only Voyage is supported today; the Protocol lets others slot in later.
    from app.rerank.voyage import VoyageReranker

    return VoyageReranker(api_key=settings.voyage_api_key, model=settings.rerank_model)
