"""Reconciliation invariants: extraction is distrusted until the math checks."""

from __future__ import annotations

from decimal import Decimal

from app.core.finance import FinancialFact, FiscalPeriod, StatementType

from ingestion.pipeline.reconcile import reconcile

FY24 = FiscalPeriod(fiscal_year=2024, quarter=None)


def fact(item: str, value: str, statement: StatementType) -> FinancialFact:
    v = Decimal(value)
    return FinancialFact(
        entity_id="ACME",
        doc_id="acme-10k-2024",
        statement=statement,
        line_item=item,
        line_item_as_reported=item.replace("_", " "),
        period=FY24,
        value=v,
        value_as_reported=v,
    )


def balance(assets: str, liabilities: str, equity: str) -> list[FinancialFact]:
    b = StatementType.BALANCE
    return [
        fact("total_assets", assets, b),
        fact("total_liabilities", liabilities, b),
        fact("total_equity", equity, b),
    ]


def test_balanced_sheet_is_clean():
    assert reconcile(balance("364980", "308030", "56950")) == []


def test_balance_identity_violation_flagged():
    issues = reconcile(balance("364980", "308030", "40000"))
    assert len(issues) == 1
    assert issues[0].check == "balance_identity"
    assert issues[0].expected == Decimal("364980")
    assert issues[0].actual == Decimal("348030")


def test_rounding_within_tolerance_passes():
    # Off by 0.1% — absorbed by the 0.5% tolerance (rounded presentations).
    assert reconcile(balance("100000", "70000", "29900")) == []


def test_gross_profit_identity():
    i = StatementType.INCOME
    clean = [
        fact("revenue", "391035", i),
        fact("cost_of_revenue", "210352", i),
        fact("gross_profit", "180683", i),
    ]
    assert reconcile(clean) == []

    broken = [
        fact("revenue", "391035", i),
        fact("cost_of_revenue", "210352", i),
        fact("gross_profit", "150000", i),
    ]
    issues = reconcile(broken)
    assert [x.check for x in issues] == ["gross_profit"]


def test_missing_inputs_are_not_violations():
    # Only revenue present: no identity is checkable, so no issues.
    assert reconcile([fact("revenue", "391035", StatementType.INCOME)]) == []
    assert reconcile([]) == []
