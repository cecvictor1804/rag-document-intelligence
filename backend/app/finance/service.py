"""Metric answering: resolve a requested figure or ratio deterministically.

The /metrics endpoint's engine. Either a direct line-item lookup ("revenue for
Q3 FY2024") or a registered ratio/growth computation — in both cases the result
carries the exact source facts (cells) used, so the response is self-citing.
No LLM anywhere in this path.
"""

from __future__ import annotations

from app.core.finance import Basis, FinancialFact, FiscalPeriod, MetricResult
from app.core.interfaces import MetricStore
from app.finance.chart import line_item as chart_item
from app.finance.metrics import (
    RATIO_METRICS,
    MetricError,
    compute_ratio_metric,
    growth,
)


class MetricService:
    def __init__(self, store: MetricStore) -> None:
        self.store = store

    async def lookup(
        self,
        entity_id: str,
        line_item: str,
        period: FiscalPeriod,
        basis: Basis = Basis.GAAP,
        segment: str | None = None,
    ) -> FinancialFact | None:
        """The authoritative reported value of one canonical line item."""
        if chart_item(line_item) is None:
            raise MetricError(f"unknown line item: {line_item}")
        return await self.store.get_fact(entity_id, line_item, period, basis, segment)

    async def compute(
        self,
        entity_id: str,
        metric: str,
        period: FiscalPeriod,
        basis: Basis = Basis.GAAP,
    ) -> MetricResult | None:
        """A registered ratio metric for one period, or None if facts are missing."""
        spec = RATIO_METRICS.get(metric)
        if spec is None:
            raise MetricError(f"unknown metric: {metric}")
        numerator_item, denominator_item, _ = spec
        numerator = await self.store.get_fact(entity_id, numerator_item, period, basis)
        denominator = await self.store.get_fact(
            entity_id, denominator_item, period, basis
        )
        if numerator is None or denominator is None:
            return None
        return compute_ratio_metric(metric, numerator, denominator)

    async def growth_yoy(
        self,
        entity_id: str,
        line_item: str,
        period: FiscalPeriod,
        basis: Basis = Basis.GAAP,
    ) -> MetricResult | None:
        """Year-over-year growth of a line item (same quarter, prior year)."""
        prior_period = FiscalPeriod(
            fiscal_year=period.fiscal_year - 1, quarter=period.quarter
        )
        current = await self.store.get_fact(entity_id, line_item, period, basis)
        prior = await self.store.get_fact(entity_id, line_item, prior_period, basis)
        if current is None or prior is None:
            return None
        return growth(current, prior)

    async def resolve(
        self,
        entity_id: str,
        metric: str,
        period: FiscalPeriod,
        basis: Basis = Basis.GAAP,
    ) -> MetricResult | None:
        """One entrypoint for the API: a registered ratio ("gross_margin"), a
        YoY growth ("revenue_yoy"), or a direct line-item lookup ("revenue").
        Raises MetricError for names that are none of those; returns None when
        the metric is known but the underlying facts aren't in the store."""
        if metric in RATIO_METRICS:
            return await self.compute(entity_id, metric, period, basis)
        if metric.endswith("_yoy") and chart_item(metric[: -len("_yoy")]):
            return await self.growth_yoy(
                entity_id, metric[: -len("_yoy")], period, basis
            )
        fact = await self.lookup(entity_id, metric, period, basis)
        if fact is None:
            return None
        return MetricResult(
            metric=metric,
            value=fact.value,
            unit=fact.unit,
            currency=fact.currency if fact.unit == "currency" else None,
            period=fact.period,
            formula="as reported",
            inputs=[fact],
        )
