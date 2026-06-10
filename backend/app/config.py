"""Centralized, environment-driven configuration.

Every tunable knob in the system is surfaced here so nothing is hardcoded and
no secret lives in code. Values are read from the environment (or a local
`.env` during development); in AWS they come from Secrets Manager / App Runner.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── App ──────────────────────────────────────────────────────────────
    env: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = "postgresql://rag:rag@localhost:5432/rag"

    # ── Document source ──────────────────────────────────────────────────
    doc_source: Literal["local", "s3"] = "local"
    local_docs_path: str = "./sample_docs"
    s3_bucket: str = ""
    s3_prefix: str = ""
    aws_region: str = "us-east-1"

    # ── Embeddings ───────────────────────────────────────────────────────
    embedding_provider: Literal["voyage", "openai"] = "voyage"
    embedding_model: str = "voyage-3"
    embedding_dim: int = 1024
    voyage_api_key: str = ""
    openai_api_key: str = ""

    # ── Reranker ─────────────────────────────────────────────────────────
    rerank_provider: Literal["voyage"] = "voyage"
    rerank_model: str = "rerank-2"

    # ── Chunking ─────────────────────────────────────────────────────────
    chunk_tokens: int = 600
    chunk_overlap_ratio: float = 0.15

    # ── Retrieval ────────────────────────────────────────────────────────
    dense_top_k: int = 50
    lexical_top_k: int = 50
    rrf_k: int = 60
    fuse_top_k: int = 40
    rerank_top_k: int = 8
    min_rerank_score: float = 0.3

    # ── Generation + routing ─────────────────────────────────────────────
    anthropic_api_key: str = ""
    router_enabled: bool = True
    router_model_cheap: str = "claude-haiku-4-5"
    router_model_mid: str = "claude-sonnet-4-6"
    router_model_strong: str = "claude-opus-4-8"
    router_high_confidence: float = 0.65
    router_low_confidence: float = 0.45
    router_long_context_tokens: int = 150_000
    router_default_effort: Literal["low", "medium", "high", "max"] = "medium"

    # ── Auth (Google Workspace SSO) ──────────────────────────────────────
    # When False (default) the API is open and the caller is treated as an
    # anonymous principal — this keeps local dev and tests runnable without a
    # Google OAuth client. Set True in staging/prod to enforce the SSO gate.
    auth_enabled: bool = False
    google_hosted_domain: str = ""
    google_oauth_client_id: str = ""
    oidc_audience: str = ""

    @property
    def oidc_expected_audience(self) -> str:
        """The `aud` an incoming Google ID token must carry: the OAuth client
        id, unless a distinct audience was configured."""
        return self.oidc_audience or self.google_oauth_client_id

    # ── Financial extraction (Phase 5) ───────────────────────────────────
    # "html" is the built-in parser for native-HTML filings (EDGAR). A
    # commercial parser adapter (scanned PDFs, complex tables) plugs in here.
    financial_parser: Literal["html"] = "html"

    # ── Ingestion worker ─────────────────────────────────────────────────
    ingest_sqs_queue_url: str = ""

    @property
    def chunk_overlap_tokens(self) -> int:
        return int(self.chunk_tokens * self.chunk_overlap_ratio)


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so config is parsed once per process."""
    return Settings()
