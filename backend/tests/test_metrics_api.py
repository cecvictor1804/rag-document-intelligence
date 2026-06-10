"""/metrics endpoint + the advice gate in AnswerService — fakes, no DB/LLM."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app import deps
from app.core.finance import (
    Basis,
    CellRef,
    FinancialFact,
    FiscalPeriod,
    MetricResult,
    StatementType,
)
from app.finance.guardrails import ADVICE_REFUSAL
from app.finance.metrics import MetricError
from app.finance.service import MetricService
from app.generation.service import AnswerService
from app.main import app
from fakes import FakeLLM, FakeRetrieval, make_chunk, rr, settings
from fastapi.testclient import TestClient

Q3_24 = FiscalPeriod(fiscal_year=2024, quarter=3)


def revenue_fact() -> FinancialFact:
    return FinancialFact(
        entity_id="ACME",
        doc_id="acme-10q-q3-2024",
        statement=StatementType.INCOME,
        line_item="revenue",
        line_item_as_reported="Net sales",
        period=Q3_24,
        value=Decimal("94930000000"),
        value_as_reported=Decimal("94930"),
        scale=1_000_000,
        cell=CellRef(table_index=2, row=1, col=1, page=4),
    )


class FakeMetricService:
    def __init__(self, result: MetricResult | None = None,
                 error: str | None = None) -> None:
        self.result, self.error = result, error

    async def resolve(self, entity_id, metric, period, basis=Basis.GAAP):
        if self.error:
            raise MetricError(self.error)
        return self.result


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_metrics_returns_value_with_cell_provenance():
    fact = revenue_fact()
    result = MetricResult(
        metric="revenue", value=fact.value, unit="currency", currency="USD",
        period=Q3_24, formula="as reported", inputs=[fact],
    )
    app.dependency_overrides[deps.metric_service] = lambda: FakeMetricService(result)
    client = TestClient(app)

    r = client.post("/metrics", json={
        "entity": "ACME", "metric": "revenue", "fiscal_year": 2024,
        "fiscal_quarter": 3,
    })

    assert r.status_code == 200
    body = r.json()
    assert body["value"] == "94930000000"  # Decimal exactness preserved
    assert body["period"] == "Q3 FY2024"
    assert body["disclaimer"]
    (prov,) = body["inputs"]
    # The drill-down target: exact cell in the exact document.
    assert (prov["doc_id"], prov["page"], prov["table_index"], prov["row"],
            prov["col"]) == ("acme-10q-q3-2024", 4, 2, 1, 1)
    assert prov["line_item_as_reported"] == "Net sales"
    assert prov["value_as_reported"] == "94930"


def test_metrics_404_when_facts_missing():
    app.dependency_overrides[deps.metric_service] = lambda: FakeMetricService(None)
    client = TestClient(app)
    r = client.post("/metrics", json={
        "entity": "ACME", "metric": "gross_margin", "fiscal_year": 2024,
    })
    assert r.status_code == 404


def test_metrics_422_for_unknown_metric():
    app.dependency_overrides[deps.metric_service] = lambda: FakeMetricService(
        error="unknown metric: wibble"
    )
    client = TestClient(app)
    r = client.post("/metrics", json={
        "entity": "ACME", "metric": "wibble", "fiscal_year": 2024,
    })
    assert r.status_code == 422


class EmptyStore:
    async def get_fact(self, *a, **k):
        return None

    async def get_series(self, *a, **k):
        return []

    async def upsert_document(self, meta):  # pragma: no cover — protocol stub
        pass

    async def upsert_facts(self, facts):  # pragma: no cover — protocol stub
        return 0


async def test_metric_service_resolve_rejects_unknown_names():
    service = MetricService(EmptyStore())
    with pytest.raises(MetricError):
        await service.resolve("ACME", "not_a_thing", Q3_24)


async def test_metric_service_resolve_returns_none_when_facts_missing():
    service = MetricService(EmptyStore())
    assert await service.resolve("ACME", "gross_margin", Q3_24) is None
    assert await service.resolve("ACME", "revenue", Q3_24) is None
    assert await service.resolve("ACME", "revenue_yoy", Q3_24) is None


# ── Advice gate in the narrative path ────────────────────────────────────────


async def test_advice_request_refused_without_retrieval_or_llm():
    llm = FakeLLM()
    service = AnswerService(
        FakeRetrieval([rr(make_chunk(), 0.9)]), llm, settings(), None
    )
    events = [ev async for ev in service.answer("Should I buy ACME stock?")]

    assert events[0].data["reason"] == "advice guardrail"
    assert events[1].data == ADVICE_REFUSAL
    assert events[-1].type.value == "done"
    assert llm.calls == 0  # Claude was never called


async def test_factual_question_still_answers():
    llm = FakeLLM()
    service = AnswerService(
        FakeRetrieval([rr(make_chunk(), 0.9)]), llm, settings(), None
    )
    events = [ev async for ev in service.answer("What was Q3 revenue?")]
    assert llm.calls == 1
    assert any(ev.type.value == "token" for ev in events)
