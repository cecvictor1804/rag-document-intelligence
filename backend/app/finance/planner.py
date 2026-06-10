"""NL→query planner: decide which verified figures a chat question needs.

One cheap, fast Claude call (the router's cheap tier) maps the question to a
small structured plan: which entity, which metrics from the **legal vocabulary**
(canonical chart items, registered ratios, `<item>_yoy`), which periods, and
whether a multi-period series (chart) was asked for. The plan is executed
deterministically by MetricService — the planner only ever *selects* metrics,
it never produces numbers.

Failure posture: ANY error (transport, malformed JSON, unknown metrics, missing
entity) yields ``None``, which means "answer with narrative RAG only" — the
feature degrades, never breaks. The transport is an injectable async callable
so tests run without the SDK.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import anthropic

from app.finance.chart import canonical_names
from app.finance.metrics import RATIO_METRICS

logger = logging.getLogger("rag.planner")

# transport(system, user, model) -> the model's text response
Transport = Callable[[str, str, str], Awaitable[str]]

_MAX_REQUESTS = 4


@dataclass(slots=True)
class PlannedRequest:
    metric: str
    fiscal_year: int | None = None
    fiscal_quarter: int | None = None
    series: bool = False
    segment: str | None = None  # business segment, when the user named one


@dataclass(slots=True)
class QueryPlan:
    entity: str
    requests: list[PlannedRequest] = field(default_factory=list)


def metric_vocabulary() -> list[str]:
    """Every metric name the planner is allowed to request."""
    items = canonical_names()
    return items + list(RATIO_METRICS) + [f"{i}_yoy" for i in items]


_SYSTEM = (
    "You extract structured financial-data requests from a user question about "
    "company filings. Respond with ONLY a JSON object, no prose, shaped as:\n"
    '{"needs_financial_data": bool, "entity": string|null, "requests": '
    '[{"metric": string, "fiscal_year": int|null, "fiscal_quarter": 1|2|3|4|null, '
    '"series": bool, "segment": string|null}]}\n\n'
    "Rules:\n"
    "- needs_financial_data is true ONLY if the question explicitly asks about "
    "reported figures, metrics, ratios, growth, or trends of a specific company.\n"
    "- entity: the ticker or short company identifier the user referred to, "
    "null if no specific company is identifiable.\n"
    "- metric MUST be one of the allowed names (next message). Never invent names.\n"
    "- Plan only what was explicitly asked; at most "
    f"{_MAX_REQUESTS} requests.\n"
    "- fiscal_year/fiscal_quarter null when the user did not state a period "
    "(the system resolves 'latest'). fiscal_quarter null also means full year.\n"
    '- series: true when a trend over multiple periods was asked ("over time", '
    '"last N quarters", "trend") — then leave the period fields null.\n'
    "- segment: set ONLY when the user explicitly named a business segment "
    '(e.g. "Widgets Pro revenue"); null otherwise.\n'
    "- Questions that are purely qualitative (why/how/risks/summaries) with no "
    "figure request => needs_financial_data: false."
)

_JSON_RE = re.compile(r"\{.*\}", re.S)


def parse_plan(text: str) -> QueryPlan | None:
    """Strict, vocabulary-checked parse of the model's JSON. None on any doubt."""
    m = _JSON_RE.search(text)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data.get("needs_financial_data"):
        return None
    entity = data.get("entity")
    if not isinstance(entity, str) or not entity.strip():
        return None

    vocabulary = set(metric_vocabulary())
    requests: list[PlannedRequest] = []
    for raw in data.get("requests", [])[:_MAX_REQUESTS]:
        if not isinstance(raw, dict):
            continue
        metric = raw.get("metric")
        if metric not in vocabulary:
            continue
        year = raw.get("fiscal_year")
        quarter = raw.get("fiscal_quarter")
        segment = raw.get("segment")
        requests.append(
            PlannedRequest(
                metric=metric,
                fiscal_year=year if isinstance(year, int) else None,
                fiscal_quarter=quarter if quarter in (1, 2, 3, 4) else None,
                series=bool(raw.get("series")),
                segment=segment.strip()
                if isinstance(segment, str) and segment.strip()
                else None,
            )
        )
    if not requests:
        return None
    return QueryPlan(entity=entity.strip().upper(), requests=requests)


class LLMQueryPlanner:
    """QueryPlanner backed by a small Claude call (or any injected transport)."""

    def __init__(
        self, model: str, api_key: str = "", transport: Transport | None = None
    ) -> None:
        self.model = model
        self._transport = transport or self._anthropic_transport
        self._client = (
            None if transport else anthropic.AsyncAnthropic(api_key=api_key or None)
        )

    async def _anthropic_transport(self, system: str, user: str, model: str) -> str:
        assert self._client is not None
        response = await self._client.messages.create(
            model=model, max_tokens=500, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        )

    async def plan(self, query: str) -> QueryPlan | None:
        user = (
            f"Allowed metric names:\n{', '.join(metric_vocabulary())}\n\n"
            f"Question: {query}"
        )
        try:
            text = await self._transport(_SYSTEM, user, self.model)
        except Exception as exc:  # noqa: BLE001 — planner must degrade, not break
            logger.warning("planner call failed: %s", exc)
            return None
        return parse_plan(text)
