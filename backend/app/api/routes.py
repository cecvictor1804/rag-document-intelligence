"""API routes.

`/query` streams the answer as Server-Sent Events — one SSE per `AnswerEvent`
(`event:` = its type, `data:` = JSON payload), so the client renders tokens live
and gets citations + routing metadata inline. `/feedback` records a rating;
`/health` reports DB readiness.

The engine is reached through `app.deps` callables used as FastAPI dependencies,
so tests override them via `app.dependency_overrides` without a DB or API keys.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sse_starlette.sse import EventSourceResponse

from app import deps
from app.api.schemas import (
    BasisAlternative,
    ConvertedValue,
    FactProvenance,
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    MetricRequest,
    MetricResponse,
    QueryRequest,
    ReviewIssue,
    ReviewResponse,
)
from app.auth import Principal, require_user
from app.core.finance import Basis, FinancialFact, FiscalPeriod
from app.core.interfaces import MetricStore
from app.core.models import AnswerEvent, AnswerEventType
from app.db.pool import get_pool
from app.feedback import Feedback
from app.finance.fx import convert
from app.finance.guardrails import DISCLAIMER
from app.finance.metrics import MetricError
from app.finance.service import MetricService
from app.generation.service import AnswerService

logger = logging.getLogger("rag.api")
router = APIRouter()


def _sse(ev: AnswerEvent) -> dict:
    """Serialize one AnswerEvent to an SSE frame (event name + JSON data)."""
    data = ev.data
    if ev.type == AnswerEventType.CITATIONS:
        data = [asdict(c) for c in ev.data]
    return {"event": ev.type.value, "data": json.dumps(data, default=str)}


@router.post("/query")
async def query(
    req: QueryRequest,
    service: Annotated[AnswerService, Depends(deps.answer_service)],
    user: Annotated[Principal, Depends(require_user)],
) -> EventSourceResponse:
    history = [t.to_turn() for t in req.history]

    async def events() -> AsyncIterator[dict]:
        async for ev in service.answer(req.query, history):
            yield _sse(ev)

    return EventSourceResponse(events())


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(
    req: FeedbackRequest,
    sink: Annotated[Feedback, Depends(deps.feedback)],
    user: Annotated[Principal, Depends(require_user)],
) -> FeedbackResponse:
    fid = await sink.record(
        query=req.query,
        answer=req.answer,
        rating=req.rating,
        comment=req.comment,
        chunk_ids=req.chunk_ids,
        user_email=user.email,
    )
    return FeedbackResponse(id=fid)


def _provenance(fact: FinancialFact) -> FactProvenance:
    return FactProvenance(
        line_item=fact.line_item,
        line_item_as_reported=fact.line_item_as_reported,
        value=str(fact.value),
        value_as_reported=str(fact.value_as_reported),
        scale=fact.scale,
        currency=fact.currency,
        unit=fact.unit,
        basis=fact.basis.value,
        segment=fact.segment,
        period=fact.period.label,
        doc_id=fact.doc_id,
        page=fact.cell.page if fact.cell else None,
        table_index=fact.cell.table_index if fact.cell else None,
        row=fact.cell.row if fact.cell else None,
        col=fact.cell.col if fact.cell else None,
    )


@router.post("/metrics", response_model=MetricResponse)
async def metrics(
    req: MetricRequest,
    service: Annotated[MetricService, Depends(deps.metric_service)],
    user: Annotated[Principal, Depends(require_user)],
) -> MetricResponse:
    """Deterministic figure lookup/computation — no LLM in this path. Every
    value carries the exact source cells it came from; FX conversion and the
    non-GAAP counterpart are annotated extras, never silent substitutions."""
    period = FiscalPeriod(fiscal_year=req.fiscal_year, quarter=req.fiscal_quarter)
    try:
        result = await service.resolve(
            req.entity, req.metric, period, Basis(req.basis), segment=req.segment
        )
    except MetricError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No authoritative facts for {req.metric} "
            f"({req.entity}, {period.label})",
        )

    converted: ConvertedValue | None = None
    if (
        req.currency
        and result.unit == "currency"
        and result.currency
        and req.currency.upper() != result.currency
    ):
        as_of = result.period.end_date
        fx = await service.store.get_fx_rate(
            result.currency, req.currency.upper(), as_of
        )
        if fx is not None:
            rate, rate_date = fx
            converted = ConvertedValue(
                currency=req.currency.upper(),
                value=str(convert(result.value, rate)),
                rate=str(rate),
                rate_date=rate_date.isoformat() if rate_date else None,
            )

    alternative: BasisAlternative | None = None
    counterpart_item = result.inputs[0].line_item if len(result.inputs) == 1 else None
    if counterpart_item:
        other = await service.basis_counterpart(
            req.entity, counterpart_item, result.period, Basis(req.basis)
        )
        if other is not None:
            alternative = BasisAlternative(
                basis=other.basis.value,
                value=str(other.value),
                label=other.line_item_as_reported,
            )

    return MetricResponse(
        metric=result.metric,
        value=str(result.value),
        unit=result.unit,
        currency=result.currency,
        period=result.period.label,
        formula=result.formula,
        inputs=[_provenance(f) for f in result.inputs],
        converted=converted,
        non_gaap_alternative=alternative,
        disclaimer=DISCLAIMER,
    )


@router.get("/review", response_model=ReviewResponse)
async def review(
    store: Annotated[MetricStore, Depends(deps.metric_store)],
    user: Annotated[Principal, Depends(require_user)],
) -> ReviewResponse:
    """Open reconciliation issues — extractions a human should look at."""
    issues = await store.list_open_issues(limit=50)
    return ReviewResponse(issues=[ReviewIssue(**i) for i in issues])


async def db_ready() -> bool:
    """True if a trivial query against the pool succeeds. Never raises."""
    try:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 — health must report, not crash
        logger.warning("health: db check failed", exc_info=True)
        return False


@router.get("/health", response_model=HealthResponse)
async def health(
    response: Response, ok: Annotated[bool, Depends(db_ready)]
) -> HealthResponse:
    if not ok:
        response.status_code = 503
    return HealthResponse(status="ok" if ok else "degraded", db="ok" if ok else "down")
