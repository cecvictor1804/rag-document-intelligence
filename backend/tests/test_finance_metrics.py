"""Deterministic compute layer: exact math, hard errors on incomparable inputs."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.core.finance import (
    Basis,
    FinancialFact,
    FiscalPeriod,
    StatementType,
)
from app.finance.metrics import (
    MetricError,
    compute_ratio_metric,
    free_cash_flow,
    growth,
    margin,
    ratio,
)


def fact(
    item: str,
    value: str,
    fy: int = 2024,
    q: int | None = 3,
    currency: str = "USD",
    entity: str = "ACME",
    basis: Basis = Basis.GAAP,
    statement: StatementType = StatementType.INCOME,
) -> FinancialFact:
    v = Decimal(value)
    return FinancialFact(
        entity_id=entity,
        doc_id="10q-2024",
        statement=statement,
        line_item=item,
        line_item_as_reported=item.replace("_", " "),
        period=FiscalPeriod(fiscal_year=fy, quarter=q),
        value=v,
        value_as_reported=v,
        currency=currency,
        basis=basis,
    )


def test_yoy_growth_exact():
    current = fact("revenue", "94930000000", fy=2024)
    prior = fact("revenue", "89498000000", fy=2023)
    result = growth(current, prior)
    expected = (
        (Decimal("94930000000") - Decimal("89498000000"))
        / Decimal("89498000000") * 100
    ).quantize(Decimal("0.001"))
    assert result.metric == "revenue_yoy"
    assert result.value == expected
    assert result.unit == "percent"
    assert result.inputs == [current, prior]  # provenance carried


def test_growth_handles_negative_prior():
    current = fact("net_income", "500", fy=2024)
    prior = fact("net_income", "-1000", fy=2023)
    # (500 - (-1000)) / |-1000| = +150%
    assert growth(current, prior).value == Decimal("150.000")


def test_gross_margin():
    gp = fact("gross_profit", "43879")
    rev = fact("revenue", "94930")
    result = margin(gp, rev, "gross_margin")
    assert result.value == (Decimal("43879") / Decimal("94930") * 100).quantize(
        Decimal("0.001")
    )
    assert result.formula == "gross_profit / revenue"


def test_current_ratio():
    ca = fact("total_current_assets", "152987", statement=StatementType.BALANCE)
    cl = fact("total_current_liabilities", "176392", statement=StatementType.BALANCE)
    result = compute_ratio_metric("current_ratio", ca, cl)
    assert result.value == (Decimal("152987") / Decimal("176392")).quantize(
        Decimal("0.001")
    )
    assert result.unit == "ratio"


def test_free_cash_flow_sign_conventions():
    ocf = fact("operating_cash_flow", "110543", statement=StatementType.CASH_FLOW)
    capex_negative = fact(
        "capital_expenditures", "-10959", statement=StatementType.CASH_FLOW
    )
    capex_positive = fact(
        "capital_expenditures", "10959", statement=StatementType.CASH_FLOW
    )
    assert free_cash_flow(ocf, capex_negative).value == Decimal("99584")
    assert free_cash_flow(ocf, capex_positive).value == Decimal("99584")


def test_incomparable_inputs_raise():
    with pytest.raises(MetricError, match="currency"):
        margin(fact("gross_profit", "1", currency="EUR"), fact("revenue", "2"), "m")
    with pytest.raises(MetricError, match="period"):
        margin(fact("gross_profit", "1", fy=2023), fact("revenue", "2", fy=2024), "m")
    with pytest.raises(MetricError, match="entity"):
        margin(fact("gross_profit", "1", entity="A"), fact("revenue", "2"), "m")
    with pytest.raises(MetricError, match="basis"):
        margin(
            fact("gross_profit", "1", basis=Basis.NON_GAAP), fact("revenue", "2"), "m"
        )
    with pytest.raises(MetricError, match="zero"):
        ratio(fact("total_liabilities", "1"), fact("total_equity", "0"), "d2e")
    with pytest.raises(MetricError, match="line-item"):
        growth(fact("revenue", "1", fy=2024), fact("net_income", "1", fy=2023))
