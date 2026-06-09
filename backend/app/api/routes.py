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

from fastapi import APIRouter, Depends, Response
from sse_starlette.sse import EventSourceResponse

from app import deps
from app.api.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    QueryRequest,
)
from app.auth import Principal, require_user
from app.core.models import AnswerEvent, AnswerEventType
from app.db.pool import get_pool
from app.feedback import Feedback
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
