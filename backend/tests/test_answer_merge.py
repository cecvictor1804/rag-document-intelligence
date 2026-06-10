"""Unified answers: planner-resolved figures merged into the stream, with
post-stream verification. All fakes — no DB, no API keys."""

from __future__ import annotations

from decimal import Decimal

from app.core.finance import (
    Basis,
    CellRef,
    FinancialFact,
    FiscalPeriod,
    StatementType,
)
from app.core.models import AnswerEvent, AnswerEventType
from app.finance.planner import PlannedRequest, QueryPlan
from app.finance.service import MetricService
from app.generation.service import AnswerService
from fakes import FakeLLM, FakeRetrieval, make_chunk, rr, settings

Q3_24 = FiscalPeriod(fiscal_year=2024, quarter=3)
Q3_23 = FiscalPeriod(fiscal_year=2023, quarter=3)


def fact(item: str, value: str, period: FiscalPeriod) -> FinancialFact:
    v = Decimal(value)
    return FinancialFact(
        entity_id="ACME",
        doc_id="acme-10q",
        statement=StatementType.INCOME,
        line_item=item,
        line_item_as_reported=item.replace("_", " "),
        period=period,
        value=v,
        value_as_reported=v,
        cell=CellRef(table_index=0, row=1, col=1, page=4),
    )


class SeededStore:
    """In-memory MetricStore seeded with revenue + gross_profit for two periods."""

    def __init__(self) -> None:
        self.facts = [
            fact("revenue", "94930000000", Q3_24),
            fact("revenue", "89498000000", Q3_23),
            fact("gross_profit", "43879000000", Q3_24),
            fact("gross_profit", "40427000000", Q3_23),
        ]

    async def upsert_entity(self, *a, **k): ...
    async def upsert_document(self, *a, **k): ...
    async def upsert_facts(self, facts):
        return 0

    async def get_fact(self, entity_id, line_item, period,
                       basis=Basis.GAAP, segment=None):
        for f in self.facts:
            if (f.line_item == line_item and f.period.fiscal_year == period.fiscal_year
                    and f.period.quarter == period.quarter):
                return f
        return None

    async def get_series(self, entity_id, line_item,
                         basis=Basis.GAAP, segment=None, limit=12):
        matched = [f for f in self.facts if f.line_item == line_item]
        matched.sort(key=lambda f: (f.period.fiscal_year, f.period.quarter or 0),
                     reverse=True)
        return matched[:limit]


class FakePlanner:
    def __init__(self, plan: QueryPlan | None) -> None:
        self._plan = plan

    async def plan(self, query):
        return self._plan


def service(plan, llm=None):
    return AnswerService(
        FakeRetrieval([rr(make_chunk(text="Margins moved on component costs."), 0.9)]),
        llm or FakeLLM(),
        settings(),
        None,
        planner=FakePlanner(plan),
        metrics=MetricService(SeededStore()),
    )


async def collect(svc, query):
    return [ev async for ev in svc.answer(query)]


# ── merged flow ──────────────────────────────────────────────────────────────


async def test_metrics_event_with_provenance_then_tokens():
    plan = QueryPlan("ACME", [PlannedRequest("gross_margin", 2024, 3)])
    llm = FakeLLM([
        AnswerEvent(AnswerEventType.TOKEN, "Gross margin was 46.222% [1]."),
        AnswerEvent(AnswerEventType.DONE, {"model": "x", "usage": {}}),
    ])
    events = await collect(service(plan, llm), "What was gross margin in Q3 FY2024?")
    types = [e.type for e in events]

    assert types == [
        AnswerEventType.METRICS, AnswerEventType.META, AnswerEventType.TOKEN,
        AnswerEventType.VERIFICATION, AnswerEventType.DONE,
    ]
    (metric,) = events[0].data
    assert metric["metric"] == "gross_margin"
    assert metric["value"] == "46.222"
    assert metric["inputs"][0]["doc_id"] == "acme-10q"  # cell provenance carried
    # Clean verification: the narrated number is the verified one.
    assert events[3].data == {"unverified": []}
    # The LLM was given the verified-figures block, not just the raw question.
    assert "Verified figures" in llm.last["query"]
    assert "46.222" in llm.last["query"]


async def test_series_event_for_trend_questions():
    plan = QueryPlan("ACME", [PlannedRequest("revenue", series=True)])
    events = await collect(service(plan), "Revenue trend over recent quarters?")

    series = next(e for e in events if e.type is AnswerEventType.SERIES)
    assert series.data["metric"] == "revenue"
    assert [p["period"] for p in series.data["points"]] == ["Q3 FY2023", "Q3 FY2024"]
    assert series.data["points"][1]["value"] == 94930000000.0


async def test_ratio_series_for_margin_trends():
    plan = QueryPlan("ACME", [PlannedRequest("gross_margin", series=True)])
    events = await collect(service(plan), "Gross margin trend?")

    series = next(e for e in events if e.type is AnswerEventType.SERIES)
    assert series.data["metric"] == "gross_margin"
    assert series.data["unit"] == "percent"
    points = series.data["points"]
    assert [p["period"] for p in points] == ["Q3 FY2023", "Q3 FY2024"]
    expected = float(
        (Decimal("43879000000") / Decimal("94930000000") * 100).quantize(
            Decimal("0.001")
        )
    )
    assert points[1]["value"] == expected


async def test_segment_request_passed_to_lookup():
    class SegmentStore(SeededStore):
        def __init__(self) -> None:
            super().__init__()
            segment_fact = fact("revenue", "61700000000", Q3_24)
            segment_fact.segment = "Widgets Pro"
            self.facts.append(segment_fact)

        async def get_fact(self, entity_id, line_item, period,
                           basis=Basis.GAAP, segment=None):
            for f in self.facts:
                if (f.line_item == line_item and f.segment == segment
                        and f.period.fiscal_year == period.fiscal_year
                        and f.period.quarter == period.quarter):
                    return f
            return None

    plan = QueryPlan(
        "ACME", [PlannedRequest("revenue", 2024, 3, segment="Widgets Pro")]
    )
    svc = AnswerService(
        FakeRetrieval([rr(make_chunk(), 0.9)]), FakeLLM(), settings(), None,
        planner=FakePlanner(plan), metrics=MetricService(SegmentStore()),
    )
    events = await collect(svc, "Widgets Pro revenue in Q3 FY2024?")
    (metric,) = events[0].data
    assert metric["metric"] == "revenue (Widgets Pro)"
    assert metric["value"] == "61700000000"
    assert metric["inputs"][0]["segment"] == "Widgets Pro"


async def test_latest_period_resolved_when_no_period_stated():
    plan = QueryPlan("ACME", [PlannedRequest("revenue")])  # no year/quarter
    events = await collect(service(plan), "What is ACME's latest revenue?")
    (metric,) = events[0].data
    assert metric["period"] == "Q3 FY2024"  # newest fact wins
    assert metric["value"] == "94930000000"


async def test_fabricated_number_is_flagged():
    plan = QueryPlan("ACME", [PlannedRequest("gross_margin", 2024, 3)])
    llm = FakeLLM([
        AnswerEvent(AnswerEventType.TOKEN, "Margin was 46.222%, and costs fell 12.5%."),
        AnswerEvent(AnswerEventType.DONE, {"model": "x", "usage": {}}),
    ])
    events = await collect(service(plan, llm), "Gross margin Q3 FY2024?")
    verification = next(e for e in events if e.type is AnswerEventType.VERIFICATION)
    assert verification.data["unverified"] == ["12.5%"]


async def test_numbers_quoted_from_passages_are_not_flagged():
    plan = QueryPlan("ACME", [PlannedRequest("gross_margin", 2024, 3)])
    svc = AnswerService(
        FakeRetrieval([rr(make_chunk(text="Freight costs rose 3.4% in the quarter."), 0.9)]),
        FakeLLM([
            AnswerEvent(AnswerEventType.TOKEN,
                        "Margin was 46.222% [1]; freight rose 3.4% [1]."),
            AnswerEvent(AnswerEventType.DONE, {"model": "x", "usage": {}}),
        ]),
        settings(),
        None,
        planner=FakePlanner(plan),
        metrics=MetricService(SeededStore()),
    )
    events = await collect(svc, "Gross margin and why?")
    verification = next(e for e in events if e.type is AnswerEventType.VERIFICATION)
    assert verification.data["unverified"] == []


# ── degradation paths ────────────────────────────────────────────────────────


async def test_no_plan_means_classic_narrative_flow():
    events = await collect(service(None), "Summarize the risk factors.")
    types = [e.type for e in events]
    assert AnswerEventType.METRICS not in types
    assert AnswerEventType.VERIFICATION not in types  # no numeric path active
    assert types[0] is AnswerEventType.META


async def test_figures_carry_answer_when_retrieval_is_weak():
    plan = QueryPlan("ACME", [PlannedRequest("revenue", 2024, 3)])
    svc = AnswerService(
        FakeRetrieval([]),  # nothing retrieved at all
        FakeLLM(),
        settings(),
        None,
        planner=FakePlanner(plan),
        metrics=MetricService(SeededStore()),
    )
    events = await collect(svc, "ACME revenue Q3 FY2024?")
    types = [e.type for e in events]
    # Metrics emitted AND the model still narrates (no "I don't know" bail).
    assert types[0] is AnswerEventType.METRICS
    assert AnswerEventType.TOKEN in types


async def test_metrics_without_planner_unchanged():
    svc = AnswerService(
        FakeRetrieval([rr(make_chunk(), 0.9)]), FakeLLM(), settings(), None
    )
    events = await collect(svc, "What was Q3 revenue?")
    assert [e.type for e in events][0] is AnswerEventType.META
