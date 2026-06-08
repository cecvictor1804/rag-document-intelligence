"""Evaluation metrics.

Retrieval metrics (pure, deterministic, no API): hit-rate@k, MRR, recall@k over
the ranked retrieved doc_ids vs the case's expected doc_ids. Groundedness uses a
Claude judge (structured output) to score whether the generated answer is
supported by the passages it cited.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import anthropic
from app.config import Settings
from app.core.models import Citation

# ── Retrieval metrics ────────────────────────────────────────────────────────


def hit_rate_at_k(
    retrieved: Sequence[str], expected: Sequence[str], k: int
) -> float:
    """1.0 if any expected doc appears in the top-k retrieved, else 0.0."""
    top = set(retrieved[:k])
    return 1.0 if top & set(expected) else 0.0


def recall_at_k(
    retrieved: Sequence[str], expected: Sequence[str], k: int
) -> float:
    """Fraction of expected docs found in the top-k retrieved."""
    if not expected:
        return 0.0
    top = set(retrieved[:k])
    return len(top & set(expected)) / len(set(expected))


def mrr(retrieved: Sequence[str], expected: Sequence[str]) -> float:
    """Reciprocal rank of the first expected doc (0.0 if none retrieved)."""
    want = set(expected)
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in want:
            return 1.0 / rank
    return 0.0


# ── Groundedness (LLM judge) ─────────────────────────────────────────────────

_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "grounded": {"type": "boolean"},
        "score": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": ["grounded", "score", "reason"],
    "additionalProperties": False,
}

_JUDGE_SYSTEM = (
    "You are a strict grader. Given a question, an answer, and the source "
    "passages that answer cited, decide whether every claim in the answer is "
    "supported by those passages. Reply via the schema: `grounded` true only if "
    "fully supported, `score` from 0.0 (unsupported/hallucinated) to 1.0 "
    "(fully supported), and a one-sentence `reason`. An honest 'I don't know' "
    "with no claims is grounded (score 1.0)."
)


async def groundedness_judge(
    query: str,
    answer: str,
    citations: Sequence[Citation],
    settings: Settings,
    client: anthropic.AsyncAnthropic | None = None,
) -> dict:
    """Score whether `answer` is grounded in its cited passages."""
    client = client or anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or None)
    cited = "\n\n".join(f"[{c.n}] {c.title}: {c.snippet}" for c in citations) or "(none)"
    user = (
        f"Question: {query}\n\nAnswer: {answer}\n\nCited passages:\n{cited}"
    )
    resp = await client.messages.create(
        model=settings.router_model_strong,
        max_tokens=512,
        system=_JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": _JUDGE_SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "{}")
    return json.loads(text)
