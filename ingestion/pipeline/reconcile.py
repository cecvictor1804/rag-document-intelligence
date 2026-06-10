"""Reconciliation invariants: distrust extraction until the math checks out.

Run at ingest over one document's mapped facts. Each check compares figures the
document itself asserts (totals, accounting identities); a violation flags the
extraction rather than silently storing a wrong number.

Tolerance is relative (default 0.5%) to absorb rounding in "(in millions)"
presentations.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.core.finance import (
    Basis,
    FinancialFact,
    FiscalPeriod,
    ReconciliationIssue,
)

DEFAULT_TOLERANCE = Decimal("0.005")  # 0.5% relative


def _close(a: Decimal, b: Decimal, tolerance: Decimal) -> bool:
    scale = max(abs(a), abs(b), Decimal(1))
    return abs(a - b) <= scale * tolerance


def _index(
    facts: Sequence[FinancialFact],
) -> dict[tuple[str, FiscalPeriod], Decimal]:
    """(canonical line item, period) -> consolidated GAAP value."""
    out: dict[tuple[str, FiscalPeriod], Decimal] = {}
    for f in facts:
        if f.line_item and f.segment is None and f.basis is Basis.GAAP:
            out.setdefault((f.line_item, f.period), f.value)
    return out


def reconcile(
    facts: Sequence[FinancialFact],
    tolerance: Decimal = DEFAULT_TOLERANCE,
) -> list[ReconciliationIssue]:
    """All invariant violations across a document's facts (empty == clean)."""
    if not facts:
        return []
    doc_id = facts[0].doc_id
    values = _index(facts)
    periods = {p for (_, p) in values}
    issues: list[ReconciliationIssue] = []

    def check(name: str, period: FiscalPeriod, expected: Decimal, actual: Decimal) -> None:
        if not _close(expected, actual, tolerance):
            issues.append(
                ReconciliationIssue(
                    doc_id=doc_id,
                    check=name,
                    detail=f"{name} mismatch in {period.label}",
                    expected=expected,
                    actual=actual,
                )
            )

    for period in periods:
        def get(item: str) -> Decimal | None:
            return values.get((item, period))  # noqa: B023 — checked per period

        # Balance sheet identity: Assets = Liabilities + Equity.
        assets, liabilities, equity = (
            get("total_assets"), get("total_liabilities"), get("total_equity"))
        if assets is not None and liabilities is not None and equity is not None:
            check("balance_identity", period, assets, liabilities + equity)

        # Income statement: Revenue - CoR = Gross profit.
        revenue, cor, gross = (
            get("revenue"), get("cost_of_revenue"), get("gross_profit"))
        if revenue is not None and cor is not None and gross is not None:
            check("gross_profit", period, gross, revenue - cor)

        # Operating income = Gross profit - Operating expenses.
        opex, op_income = get("operating_expenses"), get("operating_income")
        if gross is not None and opex is not None and op_income is not None:
            check("operating_income", period, op_income, gross - opex)

    return issues
