"""API tests — the engine is faked at the `deps` seam (no DB, no API keys)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest
from app import deps
from app.api import routes
from app.core.models import AnswerEvent, AnswerEventType, Citation, Turn
from app.main import app
from fastapi.testclient import TestClient


class FakeAnswerService:
    """Emits the canonical event sequence; records the query + history it saw."""

    def __init__(self) -> None:
        self.seen: dict | None = None

    async def answer(
        self, query: str, history: Sequence[Turn] = (), acl_filter=None
    ) -> AsyncIterator[AnswerEvent]:
        self.seen = {"query": query, "history": list(history)}
        yield AnswerEvent(AnswerEventType.META, {"model": "claude-haiku-4-5"})
        yield AnswerEvent(AnswerEventType.TOKEN, "Meals are capped at $75/day [1].")
        yield AnswerEvent(
            AnswerEventType.CITATIONS,
            [Citation(n=1, doc_id="expense_policy.txt", title="Expenses",
                      section="Meals", source_url="file:///x", snippet="...")],
        )
        yield AnswerEvent(AnswerEventType.DONE, {"model": "claude-haiku-4-5", "usage": {}})


class FakeFeedback:
    def __init__(self) -> None:
        self.recorded: dict | None = None

    async def record(self, **kw) -> int:
        self.recorded = kw
        return 42


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_query_streams_sse_events_in_order():
    fake = FakeAnswerService()
    app.dependency_overrides[deps.answer_service] = lambda: fake
    client = TestClient(app)

    r = client.post(
        "/query",
        json={"query": "meal cap?", "history": [{"role": "user", "content": "hi"}]},
    )

    assert r.status_code == 200
    body = r.text
    # One SSE frame per AnswerEvent, in order.
    assert body.index("event: meta") < body.index("event: token")
    assert body.index("event: token") < body.index("event: citations")
    assert body.index("event: citations") < body.index("event: done")
    assert "expense_policy.txt" in body  # citation payload serialized
    # The route forwarded query + history to the service.
    assert fake.seen == {"query": "meal cap?", "history": [Turn("user", "hi")]}


def test_query_rejects_empty_query():
    app.dependency_overrides[deps.answer_service] = lambda: FakeAnswerService()
    client = TestClient(app)
    assert client.post("/query", json={"query": ""}).status_code == 422


def test_feedback_records_and_returns_id():
    sink = FakeFeedback()
    app.dependency_overrides[deps.feedback] = lambda: sink
    client = TestClient(app)

    r = client.post(
        "/feedback",
        json={"query": "q", "answer": "a", "rating": 1, "chunk_ids": [3, 5]},
    )

    assert r.status_code == 200
    assert r.json() == {"id": 42}
    assert sink.recorded["rating"] == 1
    assert sink.recorded["chunk_ids"] == [3, 5]


def test_feedback_rejects_bad_rating():
    app.dependency_overrides[deps.feedback] = lambda: FakeFeedback()
    client = TestClient(app)
    assert client.post("/feedback", json={"query": "q", "rating": 5}).status_code == 422


def test_health_ok_when_db_ready():
    app.dependency_overrides[routes.db_ready] = lambda: True
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_health_degraded_when_db_down():
    app.dependency_overrides[routes.db_ready] = lambda: False
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "degraded", "db": "down"}
