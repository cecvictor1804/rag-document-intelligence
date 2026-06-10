"""Deterministic metric computation — arithmetic happens HERE, never in the LLM.

Pure functions over FinancialFacts. Every MetricResult carries the exact input
facts (with their cell provenance), so each computed figure can cite the cells
it was derived from, and the citation-faithfulness verifier can hold an answer
to those values.

Inputs are validated (same entity, same period for ratios, same currency) and
raise MetricError rather than silently mixing incomparable figures.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.core.finance import FinancialFact, MetricResult

_PCT_QUANT = Decimal("0.001")  # percent values to 0.1 bp of a point
_RATIO_QUANT = Decimal("0.001")


class MetricError(ValueError):
    """Raised when inputs are missing, zero-denominator, or incomparable."""


def _require_comparable(
    a: FinancialFact, b: FinancialFact, *, same_period: bool
) -> None:
    if a.entity_id != b.entity_id:
        raise MetricError(f"entity mismatch: {a.entity_id} vs {b.entity_id}")
    if a.currency != b.currency:
        raise MetricError(f"currency mismatch: {a.currency} vs {b.currency}")
    if a.basis != b.basis:
        raise MetricError(f"basis mismatch: {a.basis} vs {b.basis}")
    if same_period and a.period != b.period:
        raise MetricError(f"period mismatch: {a.period.label} vs {b.period.label}")


def _pct(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        raise MetricError("division by zero")
    return (numerator / denominator * 100).quantize(_PCT_QUANT, ROUND_HALF_UP)


def growth(current: FinancialFact, prior: FinancialFact) -> MetricResult:
    """Percent change between two periods of the same line item (YoY/QoQ)."""
    _require_comparable(current, prior, same_period=False)
    item = current.line_item or current.line_item_as_reported
    prior_item = prior.line_item or prior.line_item_as_reported
    if item != prior_item:
        raise MetricError(f"line-item mismatch: {item} vs {prior_item}")
    if prior.value == 0:
        raise MetricError("prior-period value is zero")
    yoy = (
        current.period.quarter == prior.period.quarter
        and current.period.fiscal_year == prior.period.fiscal_year + 1
    )
    name = f"{item}_{'yoy' if yoy else 'growth'}"
    value = _pct(current.value - prior.value, abs(prior.value))
    return MetricResult(
        metric=name,
        value=value,
        unit="percent",
        period=current.period,
        formula=f"({item}[{current.period.label}] - {item}[{prior.period.label}])"
        f" / |{item}[{prior.period.label}]|",
        inputs=[current, prior],
    )


def margin(numerator: FinancialFact, revenue: FinancialFact, name: str) -> MetricResult:
    """A profitability margin: numerator / revenue, as a percent."""
    _require_comparable(numerator, revenue, same_period=True)
    value = _pct(numerator.value, revenue.value)
    num_item = numerator.line_item or numerator.line_item_as_reported
    return MetricResult(
        metric=name,
        value=value,
        unit="percent",
        period=numerator.period,
        formula=f"{num_item} / revenue",
        inputs=[numerator, revenue],
    )


def ratio(
    numerator: FinancialFact, denominator: FinancialFact, name: str
) -> MetricResult:
    """A balance-sheet ratio: numerator / denominator (same period)."""
    _require_comparable(numerator, denominator, same_period=True)
    if denominator.value == 0:
        raise MetricError("division by zero")
    value = (numerator.value / denominator.value).quantize(_RATIO_QUANT, ROUND_HALF_UP)
    num = numerator.line_item or numerator.line_item_as_reported
    den = denominator.line_item or denominator.line_item_as_reported
    return MetricResult(
        metric=name,
        value=value,
        unit="ratio",
        period=numerator.period,
        formula=f"{num} / {den}",
        inputs=[numerator, denominator],
    )


def free_cash_flow(ocf: FinancialFact, capex: FinancialFact) -> MetricResult:
    """FCF = operating cash flow - capital expenditures.

    Capex is conventionally reported as a negative (cash outflow); we subtract
    its magnitude so both sign conventions yield the same result.
    """
    _require_comparable(ocf, capex, same_period=True)
    value = ocf.value - abs(capex.value)
    return MetricResult(
        metric="free_cash_flow",
        value=value,
        unit="currency",
        currency=ocf.currency,
        period=ocf.period,
        formula="operating_cash_flow - |capital_expenditures|",
        inputs=[ocf, capex],
    )


# Registry the metric service exposes: metric name -> (numerator, denominator)
# canonical line items, computed via margin()/ratio() over one period.
RATIO_METRICS: dict[str, tuple[str, str, str]] = {
    # name: (numerator line item, denominator line item, kind)
    "gross_margin": ("gross_profit", "revenue", "margin"),
    "operating_margin": ("operating_income", "revenue", "margin"),
    "net_margin": ("net_income", "revenue", "margin"),
    "current_ratio": ("total_current_assets", "total_current_liabilities", "ratio"),
    "debt_to_equity": ("total_liabilities", "total_equity", "ratio"),
}


def compute_ratio_metric(
    name: str, numerator: FinancialFact, denominator: FinancialFact
) -> MetricResult:
    spec = RATIO_METRICS.get(name)
    if spec is None:
        raise MetricError(f"unknown metric: {name}")
    if spec[2] == "margin":
        return margin(numerator, denominator, name)
    return ratio(numerator, denominator, name)
