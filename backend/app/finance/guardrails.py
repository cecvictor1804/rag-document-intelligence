"""Hard advice guardrails: factual analysis only, never recommendations.

`is_advice_request` is a deterministic pre-check run BEFORE retrieval/generation
(like the min-rerank-score gate) so advice solicitations are refused without
spending a model call. The system prompt independently constrains the model for
softer phrasings that slip past the pattern check — defense in depth.
"""

from __future__ import annotations

import re

_ADVICE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\bshould\s+(i|we|you|one)\b.{0,40}\b(buy|sell|hold|short|invest)",
        r"\b(buy|sell|hold|short)\b.{0,30}\b(stock|share|shares|position|the\s+dip)\b",
        r"\bis\s+.{0,40}\b(a\s+)?(good|bad|smart|safe)\s+(investment|buy|stock to)",
        r"\bworth\s+(buying|investing|holding|selling)\b",
        r"\bprice\s+target\b",
        r"\b(which|what)\s+stocks?\s+(should|to)\s+(i|we|you)?\s*(buy|sell|pick|invest)",
        r"\brecommend\w*\b.{0,40}\b(stocks?|shares?|buy\w*|sell\w*|invest\w*|portfolio)",
        r"\ballocate\b.{0,40}\bportfolio\b",
        r"\bwill\s+the\s+(stock|share\s*price)\b.{0,30}\b(go\s+up|rise|fall|drop)",
    )
)

ADVICE_REFUSAL = (
    "I can't provide investment advice or buy/sell/hold recommendations. "
    "I can help with factual analysis of the financial documents — reported "
    "figures, computed metrics like growth and margins, and what management "
    "disclosed — and every number will cite its source."
)

DISCLAIMER = (
    "Figures are sourced from the cited documents; this is factual analysis, "
    "not investment advice."
)


def is_advice_request(query: str) -> bool:
    return any(p.search(query) for p in _ADVICE_PATTERNS)
