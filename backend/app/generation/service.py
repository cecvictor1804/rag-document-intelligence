"""Answer orchestration.

Two pre-generation gates short-circuit WITHOUT calling Claude: an investment-
advice request is refused outright (hard guardrail), and a best-reranked-chunk
score below `min_rerank_score` returns an honest "I don't know" (saves cost and
prevents hallucination on out-of-corpus questions). Otherwise route to a model
and stream the grounded, cited answer. Emits, in order: META, TOKEN*,
CITATIONS, DONE.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Sequence

from app.config import Settings
from app.core.interfaces import LLMClient
from app.core.models import AnswerEvent, AnswerEventType, Turn
from app.finance.guardrails import ADVICE_REFUSAL, is_advice_request
from app.generation.query_log import QueryLog
from app.llm.client import _NO_ANSWER
from app.llm.router import route
from app.retrieval.service import RetrievalService

logger = logging.getLogger("rag.generation")


class AnswerService:
    def __init__(
        self,
        retrieval: RetrievalService,
        llm: LLMClient,
        settings: Settings,
        query_log: QueryLog | None = None,
    ) -> None:
        self.retrieval = retrieval
        self.llm = llm
        self.settings = settings
        self.query_log = query_log

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

        context = await self.retrieval.retrieve(query, acl_filter)
        top = context[0].rerank_score if context else 0.0

        if not context or top < self.settings.min_rerank_score:
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
        async for ev in self.llm.stream_grounded_answer(
            query, context, decision.model, decision.effort, history
        ):
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
