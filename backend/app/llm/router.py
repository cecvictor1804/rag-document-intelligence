"""Cost-aware model router.

Picks the cheapest Claude model that should answer the query well, based on the
top reranker score (a confidence proxy) and the size of the retrieved context:

  - very long context        -> strong model (Opus, 1M context), high effort
  - high reranker confidence -> cheap model (Haiku), low effort
  - low reranker confidence  -> strong model (Opus), high effort  (hard/ambiguous)
  - everything else          -> mid model (Sonnet), default effort

All thresholds and model IDs come from Settings; nothing is hardcoded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.config import Settings
from app.core.models import RerankResult
from app.core.tokens import estimate_tokens


@dataclass(frozen=True, slots=True)
class RouteDecision:
    model: str
    effort: str
    reason: str


def route(
    query: str, context: Sequence[RerankResult], settings: Settings
) -> RouteDecision:
    s = settings
    if not s.router_enabled:
        return RouteDecision(s.router_model_mid, s.router_default_effort, "router disabled")

    top = context[0].rerank_score if context else 0.0
    ctx_tokens = sum(estimate_tokens(c.chunk.text) for c in context)

    if ctx_tokens >= s.router_long_context_tokens:
        return RouteDecision(
            s.router_model_strong, "high", f"long context ({ctx_tokens} tok)"
        )
    if top >= s.router_high_confidence:
        return RouteDecision(
            s.router_model_cheap, "low", f"high confidence ({top:.2f})"
        )
    if top < s.router_low_confidence:
        return RouteDecision(
            s.router_model_strong, "high", f"low confidence ({top:.2f})"
        )
    return RouteDecision(
        s.router_model_mid, s.router_default_effort, f"typical ({top:.2f})"
    )
