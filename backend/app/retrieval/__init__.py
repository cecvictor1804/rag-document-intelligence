"""Hybrid retrieval: dense + lexical search, fused and reranked."""

from __future__ import annotations

from app.retrieval.fusion import rrf_fuse
from app.retrieval.service import RetrievalService

__all__ = ["RetrievalService", "rrf_fuse"]
