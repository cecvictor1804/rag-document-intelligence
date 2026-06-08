"""Anthropic (Claude) generation: stream a grounded, cited answer.

The retrieved context is presented as numbered blocks; the model is told to
answer only from them and cite claims with inline ``[n]`` markers. After the
stream we resolve the markers it actually used into `Citation`s. Model/effort
are chosen upstream by the router; `_tier_kwargs` translates them into the
request parameters each model tier accepts (see the table below).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from typing import Any

import anthropic

from app.core.models import (
    AnswerEvent,
    AnswerEventType,
    Citation,
    RerankResult,
    Turn,
)

SYSTEM_PROMPT = (
    "You answer questions about internal company documentation. Use ONLY the "
    "numbered context passages provided in the user message. Cite every claim "
    "with inline markers like [1] or [2] that refer to the passage numbers. If "
    "the context does not contain the answer, say you don't know and do not "
    "cite anything — never use outside knowledge or guess. Be concise."
)

_NO_ANSWER = "I don't know — the documentation doesn't cover that."

# effort -> max output tokens. Grounded answers are short; keep these modest.
_MAX_TOKENS = {"low": 512, "medium": 1024, "high": 2048, "max": 4096}

_CITE_RE = re.compile(r"\[(\d+)\]")


def build_context_block(context: Sequence[RerankResult]) -> str:
    """Render the reranked chunks as numbered, attributed passages."""
    lines: list[str] = []
    for n, rr in enumerate(context, start=1):
        c = rr.chunk
        header = f"[{n}] {c.title}"
        if c.section:
            header += f" — {c.section}"
        lines.append(f"{header}\n{c.text}")
    return "\n\n".join(lines)


def extract_citations(
    answer: str, context: Sequence[RerankResult]
) -> list[Citation]:
    """Resolve the ``[n]`` markers the model actually used into Citations.

    Markers are 1-based indices into `context`; out-of-range markers are
    ignored. Returns one Citation per distinct valid marker, in first-use order.
    """
    seen: list[int] = []
    for m in _CITE_RE.finditer(answer):
        n = int(m.group(1))
        if 1 <= n <= len(context) and n not in seen:
            seen.append(n)
    citations: list[Citation] = []
    for n in seen:
        c = context[n - 1].chunk
        citations.append(
            Citation(
                n=n,
                doc_id=c.doc_id,
                title=c.title,
                section=c.section,
                source_url=c.source_url,
                snippet=c.text[:240],
            )
        )
    return citations


def _tier_kwargs(model: str, effort: str) -> dict:
    """Per-tier request params. Sending unsupported ones is a 400, so gate them:

    | model    | thinking            | output_config.effort        |
    |----------|---------------------|-----------------------------|
    | haiku-4.5| (omit)              | (omit — Haiku rejects effort)|
    | sonnet-4.6| (omit, for latency)| clamp ``max`` -> ``high``    |
    | opus-4.x | ``adaptive``        | pass through (low..max)      |
    """
    if "haiku" in model:
        return {}
    if "opus" in model:
        return {"thinking": {"type": "adaptive"}, "output_config": {"effort": effort}}
    # sonnet: no adaptive thinking (first-token latency); no max/xhigh tier.
    return {"output_config": {"effort": "high" if effort == "max" else effort}}


def _usage_dict(usage: object) -> dict:
    if usage is None:
        return {}
    return {
        k: getattr(usage, k)
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        )
        if getattr(usage, k, None) is not None
    }


class AnthropicLLMClient:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key or None)

    async def stream_grounded_answer(
        self,
        query: str,
        context: Sequence[RerankResult],
        model: str,
        effort: str,
        history: Sequence[Turn] = (),
    ) -> AsyncIterator[AnswerEvent]:
        # Typed as Any: these are well-formed Anthropic params, but spelling out
        # the SDK's TextBlockParam / MessageParam TypedDicts here adds no safety.
        system: list[Any] = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                # Stable prefix — lets multi-turn follow-ups reuse the cache.
                "cache_control": {"type": "ephemeral"},
            }
        ]
        user = f"Context passages:\n\n{build_context_block(context)}\n\nQuestion: {query}"
        messages: list[Any] = [
            *({"role": t.role, "content": t.content} for t in history),
            {"role": "user", "content": user},
        ]
        max_tokens = _MAX_TOKENS.get(effort, 1024)

        parts: list[str] = []
        final = None
        async with self._client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            **_tier_kwargs(model, effort),
        ) as stream:
            async for text in stream.text_stream:
                parts.append(text)
                yield AnswerEvent(AnswerEventType.TOKEN, text)
            final = await stream.get_final_message()

        answer = "".join(parts)
        citations = extract_citations(answer, context)
        if citations:
            yield AnswerEvent(AnswerEventType.CITATIONS, citations)
        yield AnswerEvent(
            AnswerEventType.DONE,
            {"model": model, "usage": _usage_dict(getattr(final, "usage", None))},
        )
