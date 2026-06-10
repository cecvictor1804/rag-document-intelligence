"""Query planner: strict, vocabulary-checked parsing; degrade to None on doubt."""

from __future__ import annotations

from app.finance.planner import (
    LLMQueryPlanner,
    PlannedRequest,
    metric_vocabulary,
    parse_plan,
)

GOOD = """
{"needs_financial_data": true, "entity": "acme",
 "requests": [
   {"metric": "gross_margin", "fiscal_year": 2024, "fiscal_quarter": 3, "series": false},
   {"metric": "revenue", "fiscal_year": null, "fiscal_quarter": null, "series": true}
 ]}
"""


def test_parse_good_plan():
    plan = parse_plan(GOOD)
    assert plan is not None
    assert plan.entity == "ACME"  # normalized to upper
    assert plan.requests[0] == PlannedRequest("gross_margin", 2024, 3, False)
    assert plan.requests[1] == PlannedRequest("revenue", None, None, True)


def test_parse_tolerates_prose_wrapping():
    plan = parse_plan(f"Here is the plan:\n```json\n{GOOD}\n```")
    assert plan is not None and plan.entity == "ACME"


def test_unknown_metrics_are_dropped_not_invented():
    text = (
        '{"needs_financial_data": true, "entity": "ACME", "requests": '
        '[{"metric": "ebitda_wizardry", "series": false},'
        ' {"metric": "net_income", "fiscal_year": 2024, "series": false}]}'
    )
    plan = parse_plan(text)
    assert plan is not None
    assert [r.metric for r in plan.requests] == ["net_income"]


def test_rejects_no_data_needed_missing_entity_and_garbage():
    assert parse_plan('{"needs_financial_data": false}') is None
    assert parse_plan('{"needs_financial_data": true, "entity": null, '
                      '"requests": [{"metric": "revenue"}]}') is None
    assert parse_plan('{"needs_financial_data": true, "entity": "ACME", '
                      '"requests": []}') is None
    assert parse_plan("not json at all") is None
    assert parse_plan('{"broken": ') is None


def test_vocabulary_contains_all_three_shapes():
    vocab = metric_vocabulary()
    assert "revenue" in vocab  # chart item
    assert "gross_margin" in vocab  # ratio
    assert "revenue_yoy" in vocab  # growth


async def test_planner_uses_transport_and_degrades_on_error():
    async def good_transport(system, user, model):
        assert "Allowed metric names" in user
        assert "revenue" in user
        return GOOD

    planner = LLMQueryPlanner(model="claude-haiku-4-5", transport=good_transport)
    plan = await planner.plan("What was ACME's gross margin in Q3 2024?")
    assert plan is not None and plan.entity == "ACME"

    async def broken_transport(system, user, model):
        raise RuntimeError("api down")

    planner = LLMQueryPlanner(model="claude-haiku-4-5", transport=broken_transport)
    assert await planner.plan("anything") is None
