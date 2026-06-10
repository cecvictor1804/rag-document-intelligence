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


def underlying_line_item(metric: str) -> str | None:
    """The canonical line item a metric name is anchored to: ratios anchor to
    their numerator, `<item>_yoy` to the item, chart items to themselves."""
    if metric in RATIO_METRICS:
        return RATIO_METRICS[metric][0]
    if metric.endswith("_yoy"):
        base = metric[: -len("_yoy")]
        return base if chart_item(base) else None
    return metric if chart_item(metric) else None


class MetricService:
    def __init__(self, store: MetricStore) -> None:
        self.store = store

    async def latest_period(
        self, entity_id: str, metric: str, basis: Basis = Basis.GAAP
    ) -> FiscalPeriod | None:
        """The most recent period for which the metric's anchor item has a
        fact — resolves 'latest' when a question names no period."""
        item = underlying_line_item(metric)
        if item is None:
            return None
        latest = await self.store.get_series(entity_id, item, basis, limit=1)
        return latest[0].period if latest else None

    async def series(
        self,
        entity_id: str,
        line_item: str,
        basis: Basis = Basis.GAAP,
        limit: int = 8,
    ) -> list[FinancialFact]:
        """Authoritative period series of a canonical line item, oldest first
        (chart order)."""
        if chart_item(line_item) is None:
            raise MetricError(f"unknown line item: {line_item}")
        facts = await self.store.get_series(entity_id, line_item, basis, limit=limit)
        return list(reversed(facts))

    async def ratio_series(
        self,
        entity_id: str,
        metric: str,
        basis: Basis = Basis.GAAP,
        limit: int = 8,
    ) -> list[MetricResult]:
        """A registered ratio computed per period across the series (oldest
        first). Periods missing either input are skipped, never interpolated."""
        spec = RATIO_METRICS.get(metric)
        if spec is None:
            raise MetricError(f"unknown metric: {metric}")
        numerator_item, denominator_item, _ = spec
        numerators = await self.store.get_series(
            entity_id, numerator_item, basis, limit=limit
        )
        denominators = await self.store.get_series(
            entity_id, denominator_item, basis, limit=limit
        )
        by_period = {
            (f.period.fiscal_year, f.period.quarter): f for f in denominators
        }
        results: list[MetricResult] = []
        for numerator in reversed(numerators):  # oldest first
            denominator = by_period.get(
                (numerator.period.fiscal_year, numerator.period.quarter)
            )
            if denominator is None:
                continue
            try:
                results.append(compute_ratio_metric(metric, numerator, denominator))
            except MetricError:
                continue  # e.g. zero denominator in one period
        return results

    async def basis_counterpart(
        self,
        entity_id: str,
        line_item: str,
        period: FiscalPeriod,
        basis: Basis = Basis.GAAP,
    ) -> FinancialFact | None:
        """The same line item/period on the OTHER basis (GAAP ↔ non-GAAP) —
        surfaces adjusted figures next to reported ones instead of silently
        picking one."""
        other = Basis.NON_GAAP if basis is Basis.GAAP else Basis.GAAP
        return await self.store.get_fact(entity_id, line_item, period, other)

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
        segment: str | None = None,
    ) -> MetricResult | None:
        """One entrypoint for the API: a registered ratio ("gross_margin"), a
        YoY growth ("revenue_yoy"), or a direct line-item lookup ("revenue").
        `segment` applies to direct lookups only (ratios are consolidated).
        Raises MetricError for names that are none of those; returns None when
        the metric is known but the underlying facts aren't in the store."""
        if metric in RATIO_METRICS:
            return await self.compute(entity_id, metric, period, basis)
        if metric.endswith("_yoy") and chart_item(metric[: -len("_yoy")]):
            return await self.growth_yoy(
                entity_id, metric[: -len("_yoy")], period, basis
            )
        fact = await self.lookup(entity_id, metric, period, basis, segment)
        if fact is None:
            return None
        name = f"{metric} ({segment})" if segment else metric
        return MetricResult(
            metric=name,
            value=fact.value,
            unit=fact.unit,
            currency=fact.currency if fact.unit == "currency" else None,
            period=fact.period,
            formula="as reported",
            inputs=[fact],
        )
