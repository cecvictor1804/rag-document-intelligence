"""AnswerService: min-score gate (no LLM call) vs the routed generation path."""

from __future__ import annotations

import pytest
from app.core.models import AnswerEventType
from app.generation.service import AnswerService
from app.llm.client import _NO_ANSWER
from fakes import FakeLLM, FakeRetrieval, make_chunk, rr, settings


async def _collect(svc, query):
    return [ev async for ev in svc.answer(query)]


@pytest.mark.asyncio
async def test_below_min_score_short_circuits_without_calling_llm():
    llm = FakeLLM()
    svc = AnswerService(
        FakeRetrieval([rr(make_chunk(), score=0.1)]), llm, settings(min_rerank_score=0.3)
    )

    events = await _collect(svc, "out of corpus?")

    assert llm.calls == 0  # the whole point: no Claude call, no cost
    types = [e.type for e in events]
    assert types == [AnswerEventType.META, AnswerEventType.TOKEN, AnswerEventType.DONE]
    assert events[1].data == _NO_ANSWER
    assert events[0].data["model"] is None


@pytest.mark.asyncio
async def test_empty_context_also_short_circuits():
    llm = FakeLLM()
    svc = AnswerService(FakeRetrieval([]), llm, settings())
    events = await _collect(svc, "anything")
    assert llm.calls == 0
    assert events[1].data == _NO_ANSWER


@pytest.mark.asyncio
async def test_good_path_emits_meta_then_streams_llm_events():
    llm = FakeLLM()
    # High reranker score -> router picks the cheap model.
    svc = AnswerService(
        FakeRetrieval([rr(make_chunk(), score=0.9)]), llm, settings()
    )

    events = await _collect(svc, "how much for meals?")

    assert llm.calls == 1
    assert events[0].type == AnswerEventType.META
    assert events[0].data["model"] == "claude-haiku-4-5"
    assert llm.last["model"] == "claude-haiku-4-5"
    # META first, then the LLM's own event stream (token + done) is forwarded.
    assert [e.type for e in events[1:]] == [AnswerEventType.TOKEN, AnswerEventType.DONE]
