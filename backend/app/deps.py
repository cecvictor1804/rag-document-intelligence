"""Composition root.

Assembles the configured providers into the retrieval + answer services. These
cached singletons are the single seam a future FastAPI app imports — it never
constructs providers itself, so swapping any vendor is a config change here.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import Settings, get_settings
from app.core.interfaces import EmbeddingProvider, LLMClient, Reranker, VectorStore
from app.embeddings import build_embedding_provider
from app.feedback import Feedback, PgFeedback
from app.generation.query_log import PgQueryLog, QueryLog
from app.generation.service import AnswerService
from app.llm import build_llm_client
from app.rerank import build_reranker
from app.retrieval.service import RetrievalService
from app.vectorstore import build_vector_store


@lru_cache
def settings() -> Settings:
    return get_settings()


@lru_cache
def embedder() -> EmbeddingProvider:
    return build_embedding_provider(settings())


@lru_cache
def vector_store() -> VectorStore:
    return build_vector_store()


@lru_cache
def reranker() -> Reranker:
    return build_reranker(settings())


@lru_cache
def llm_client() -> LLMClient:
    return build_llm_client(settings())


@lru_cache
def query_log() -> QueryLog:
    return PgQueryLog()


@lru_cache
def feedback() -> Feedback:
    return PgFeedback()


@lru_cache
def retrieval_service() -> RetrievalService:
    return RetrievalService(embedder(), vector_store(), reranker(), settings())


@lru_cache
def answer_service() -> AnswerService:
    return AnswerService(retrieval_service(), llm_client(), settings(), query_log())
