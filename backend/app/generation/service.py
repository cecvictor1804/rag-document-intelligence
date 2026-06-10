"""Answer orchestration: one conversational surface over both substrates.

Two pre-generation gates short-circuit WITHOUT calling Claude: an investment-
advice request is refused outright (hard guardrail), and a best-reranked-chunk
score below `min_rerank_score` returns an honest "I don't know". Otherwise:

1. The NL→query **planner** (cheap Claude call) decides which verified figures
   the question needs; MetricService resolves them **deterministically** and
   they're emitted as METRICS / SERIES events (the UI renders cards + charts).
2. The figures are appended to the question as a "verified figures" block, so
   the narrating model uses exact values instead of computing its own.
3. After streaming, every number in the answer is checked against the verified
   values + numbers present in the retrieved passages; anything unbacked is
   emitted in a VERIFICATION event (flagged — the stream is already out).

Event order: METRICS? SERIES* META TOKEN* [CITATIONS] [VERIFICATION] DONE.
The planner degrades to None on any failure, restoring the pure-narrative path.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Sequence
from decimal import Decimal
from typing import Any

from app.config import Settings
from app.core.finance import FinancialFact, FiscalPeriod, MetricResult
from app.core.interfaces import LLMClient, QueryPlanner
from app.core.models import AnswerEvent, AnswerEventType, Turn
from app.finance.guardrails import ADVICE_REFUSAL, is_advice_request
from app.finance.metrics import RATIO_METRICS, MetricError
from app.finance.service import MetricService
from app.finance.verify import extract_numbers, unverified_numbers
from app.generation.query_log import QueryLog
from app.llm.client import _NO_ANSWER
from app.llm.router import route
from app.retrieval.service import RetrievalService

logger = logging.getLogger("rag.generation")

_MAX_PLANNED_REQUESTS = 4
_SERIES_LIMIT = 8


def _fact_payload(fact: FinancialFact) -> dict[str, Any]:
    return {
        "line_item": fact.line_item,
        "line_item_as_reported": fact.line_item_as_reported,
        "value": str(fact.value),
        "value_as_reported": str(fact.value_as_reported),
        "scale": fact.scale,
        "currency": fact.currency,
        "unit": fact.unit,
        "basis": fact.basis.value,
        "segment": fact.segment,
        "period": fact.period.label,
        "doc_id": fact.doc_id,
        "page": fact.cell.page if fact.cell else None,
        "table_index": fact.cell.table_index if fact.cell else None,
        "row": fact.cell.row if fact.cell else None,
        "col": fact.cell.col if fact.cell else None,
    }


def _metric_payload(result: MetricResult) -> dict[str, Any]:
    return {
        "metric": result.metric,
        "value": str(result.value),
        "unit": result.unit,
        "currency": result.currency,
        "period": result.period.label,
        "formula": result.formula,
        "inputs": [_fact_payload(f) for f in result.inputs],
    }


class _NumericContext:
    """Figures resolved for one question: event payloads, the verified-figures
    prompt block, and the allowed-value set for post-stream verification."""

    def __init__(self) -> None:
        self.metric_payloads: list[dict[str, Any]] = []
        self.series_payloads: list[dict[str, Any]] = []
        self.allowed: list[Decimal] = []
        self.lines: list[str] = []

    def add_metric(self, result: MetricResult) -> None:
        self.metric_payloads.append(_metric_payload(result))
        self.allowed.append(result.value)
        for fact in result.inputs:
            self.allowed.extend([fact.value, fact.value_as_reported])
        suffix = "%" if result.unit == "percent" else ""
        self.lines.append(
            f"- {result.metric} ({result.period.label}) = {result.value}{suffix}"
            f" [{result.formula}]"
        )

    def add_series(self, metric: str, facts: list[FinancialFact]) -> None:
        points = [
            {"period": f.period.label, "value": float(f.value)} for f in facts
        ]
        first = facts[0]
        self.series_payloads.append(
            {"metric": metric, "unit": first.unit, "currency": first.currency,
             "points": points}
        )
        for fact in facts:
            self.allowed.extend([fact.value, fact.value_as_reported])
        rendered = "; ".join(f"{f.period.label} = {f.value}" for f in facts)
        self.lines.append(f"- {metric} series: {rendered}")

    def add_ratio_series(self, metric: str, results: list[MetricResult]) -> None:
        """A computed-per-period series (e.g. gross margin trend)."""
        points = [
            {"period": r.period.label, "value": float(r.value)} for r in results
        ]
        first = results[0]
        self.series_payloads.append(
            {"metric": metric, "unit": first.unit, "currency": first.currency,
             "points": points}
        )
        for r in results:
            self.allowed.append(r.value)
            for fact in r.inputs:
                self.allowed.extend([fact.value, fact.value_as_reported])
        suffix = "%" if first.unit == "percent" else ""
        rendered = "; ".join(f"{r.period.label} = {r.value}{suffix}" for r in results)
        self.lines.append(f"- {metric} series: {rendered}")

    @property
    def active(self) -> bool:
        return bool(self.metric_payloads or self.series_payloads)

    def augmented_query(self, query: str) -> str:
        if not self.lines:
            return query
        return (
            f"{query}\n\nVerified figures (use these values verbatim; do not "
            f"compute or introduce other numbers):\n" + "\n".join(self.lines)
        )


class AnswerService:
    def __init__(
        self,
        retrieval: RetrievalService,
        llm: LLMClient,
        settings: Settings,
        query_log: QueryLog | None = None,
        planner: QueryPlanner | None = None,
        metrics: MetricService | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.llm = llm
        self.settings = settings
        self.query_log = query_log
        self.planner = planner
        self.metrics = metrics

    async def _resolve_plan(self, query: str) -> _NumericContext:
        """Plan + execute deterministically. Every failure path leaves the
        numeric context empty — the answer falls back to narrative-only."""
        numeric = _NumericContext()
        if self.planner is None or self.metrics is None:
            return numeric
        try:
            plan = await self.planner.plan(query)
        except Exception:  # noqa: BLE001 — planner must degrade, not break
            logger.warning("planner failed", exc_info=True)
            return numeric
        if plan is None:
            return numeric

        for request in plan.requests[:_MAX_PLANNED_REQUESTS]:
            try:
                if request.series:
                    if request.metric in RATIO_METRICS:
                        results = await self.metrics.ratio_series(
                            plan.entity, request.metric, limit=_SERIES_LIMIT
                        )
                        if results:
                            numeric.add_ratio_series(request.metric, results)
                        continue
                    facts = await self.metrics.series(
                        plan.entity, request.metric, limit=_SERIES_LIMIT
                    )
                    if facts:
                        numeric.add_series(request.metric, facts)
                    continue
                if request.fiscal_year is not None:
                    period = FiscalPeriod(
                        fiscal_year=request.fiscal_year,
                        quarter=request.fiscal_quarter,
                    )
                else:
                    latest = await self.metrics.latest_period(
                        plan.entity, request.metric
                    )
                    if latest is None:
                        continue
                    period = latest
                result = await self.metrics.resolve(
                    plan.entity, request.metric, period, segment=request.segment
                )
                if result is not None:
                    numeric.add_metric(result)
            except MetricError as exc:
                logger.info("planned metric skipped: %s", exc)
        return numeric

    async def answer(
        self,
        query: str,
        history: Sequence[Turn] = (),
        acl_filter: Sequence[str] | None = None,
    ) -> AsyncIterator[AnswerEvent]:
        started = time.perf_counter()

        # Hard guardrail: investment-advice requests are refused before any
        # retrieval or model call.
        if is_advice_request(query):
            yield AnswerEvent(
                AnswerEventType.META,
                {"model": None, "reason": "advice guardrail", "top_score": 0.0,
                 "n_results": 0},
            )
            yield AnswerEvent(AnswerEventType.TOKEN, ADVICE_REFUSAL)
            yield AnswerEvent(AnswerEventType.DONE, {"model": None, "usage": {}})
            await self._log(query, None, "advice guardrail", 0.0, 0, started)
            return

        numeric = await self._resolve_plan(query)
        if numeric.metric_payloads:
            yield AnswerEvent(AnswerEventType.METRICS, numeric.metric_payloads)
        for series in numeric.series_payloads:
            yield AnswerEvent(AnswerEventType.SERIES, series)

        context = await self.retrieval.retrieve(query, acl_filter)
        top = context[0].rerank_score if context else 0.0

        # Verified figures alone can carry an answer even when prose can't.
        if (not context or top < self.settings.min_rerank_score) and not numeric.active:
            yield AnswerEvent(
                AnswerEventType.META,
                {"model": None, "reason": "below min score", "top_score": top,
                 "n_results": len(context)},
            )
            yield AnswerEvent(AnswerEventType.TOKEN, _NO_ANSWER)
            yield AnswerEvent(AnswerEventType.DONE, {"model": None, "usage": {}})
            await self._log(query, None, "below min score", top, len(context), started)
            return

        decision = route(query, context, self.settings)
        yield AnswerEvent(
            AnswerEventType.META,
            {"model": decision.model, "effort": decision.effort,
             "reason": decision.reason, "top_score": top, "n_results": len(context)},
        )

        # Post-stream verification needs the numbers quoted in the passages
        # too, or prose-cited figures would be false-flagged.
        allowed = list(numeric.allowed)
        for rr in context:
            allowed.extend(m.value for m in extract_numbers(rr.chunk.text))

        parts: list[str] = []
        async for ev in self.llm.stream_grounded_answer(
            numeric.augmented_query(query), context,
            decision.model, decision.effort, history,
        ):
            if ev.type is AnswerEventType.TOKEN:
                parts.append(ev.data)
                yield ev
            elif ev.type is AnswerEventType.DONE:
                if numeric.active:
                    flagged = unverified_numbers("".join(parts), allowed)
                    yield AnswerEvent(
                        AnswerEventType.VERIFICATION,
                        {"unverified": [m.raw for m in flagged]},
                    )
                yield ev
            else:
                yield ev
        await self._log(
            query, decision.model, decision.reason, top, len(context), started
        )

    async def _log(
        self,
        query: str,
        model: str | None,
        reason: str,
        top: float,
        n: int,
        started: float,
    ) -> None:
        if self.query_log is None:
            return
        try:
            await self.query_log.record(
                query=query,
                model=model,
                route_reason=reason,
                top_score=top,
                n_results=n,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception:  # noqa: BLE001 — observability must not break answering
            logger.warning("query_log write failed", exc_info=True)
