"""Claude generation behind the `LLMClient` Protocol, plus the model router."""

from __future__ import annotations

from app.config import Settings
from app.core.interfaces import LLMClient
from app.llm.router import RouteDecision, route

__all__ = ["RouteDecision", "build_llm_client", "route"]


def build_llm_client(settings: Settings) -> LLMClient:
    from app.llm.client import AnthropicLLMClient

    return AnthropicLLMClient(api_key=settings.anthropic_api_key)
