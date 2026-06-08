"""Vector store implementations behind the `VectorStore` Protocol."""

from __future__ import annotations

from app.core.interfaces import VectorStore


def build_vector_store() -> VectorStore:
    from app.vectorstore.pgvector import PgVectorStore

    return PgVectorStore()
