"""Fact mapper: cells → normalized facts with provenance. Pure, no I/O."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.finance import (
    Basis,
    FinancialDocMeta,
    ParsedTable,
    SourceAuthority,
    StatementType,
)

from ingestion.pipeline.facts import (
    detect_basis,
    detect_currency,
    detect_scale,
    detect_statement,
    map_document_tables,
    map_table,
    parse_numeric,
    resolve_period,
)

DOC = FinancialDocMeta(
    doc_id="acme-10q-q3-2024",
    entity_id="ACME",
    doc_type="10-Q",
    authority=SourceAuthority.QUARTERLY_FILING,
    filed_date=date(2024, 10, 30),
)


# ── parse_numeric ────────────────────────────────────────────────────────────


def test_parse_numeric_variants():
    assert parse_numeric("1,234") == Decimal("1234")
    assert parse_numeric("(1,234)") == Decimal("-1234")
    assert parse_numeric("$ 94,930") == Decimal("94930")
    assert parse_numeric("1.64") == Decimal("1.64")
    assert parse_numeric("6%") == Decimal("6")
    assert parse_numeric("—") is None
    assert parse_numeric("-") is None
    assert parse_numeric("n/a") is None
    assert parse_numeric("Total") is None
    assert parse_numeric("Sep 30") is None


# ── context detection ────────────────────────────────────────────────────────


def test_scale_currency_statement_basis_detection():
    caption = "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS (In millions)"
    assert detect_scale(caption) == 1_000_000
    assert detect_scale("(in thousands, except per share data)") == 1_000
    assert detect_scale("$ in billions") == 1_000_000_000
    assert detect_currency("(€ in millions)") == "EUR"
    assert detect_currency(caption) == "USD"
    assert detect_statement(caption) is StatementType.INCOME
    assert detect_statement("CONSOLIDATED BALANCE SHEETS") is StatementType.BALANCE
    assert detect_statement("STATEMENTS OF CASH FLOWS") is StatementType.CASH_FLOW
    assert detect_basis("Reconciliation of Non-GAAP Measures") is Basis.NON_GAAP
    assert detect_basis("Adjusted operating income") is Basis.NON_GAAP
    assert detect_basis(caption) is Basis.GAAP


# ── periods ──────────────────────────────────────────────────────────────────


def test_resolve_period_quarterly_and_annual():
    q = resolve_period("Three Months Ended September 30, 2024")
    assert q is not None and (q.fiscal_year, q.quarter) == (2024, 3)
    assert q.end_date == date(2024, 9, 28)  # day clamped to 28

    fy = resolve_period("Twelve Months Ended December 31, 2024")
    assert fy is not None and (fy.fiscal_year, fy.quarter) == (2024, None)

    assert resolve_period("Year Ended June 30, 2024").quarter is None
    assert resolve_period("FY2023").fiscal_year == 2023
    assert resolve_period("2022").quarter is None
    assert resolve_period("% Change") is None
    assert resolve_period("") is None


# ── map_table ────────────────────────────────────────────────────────────────

INCOME_TABLE = ParsedTable(
    index=2,
    page=4,
    caption="CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS "
    "(In millions, except per share amounts)",
    rows=[
        ["", "Three Months Ended September 30, 2024",
         "Three Months Ended September 30, 2023", "% Change"],
        ["Net sales", "$ 94,930", "89,498", "6%"],
        ["Cost of sales", "(51,051)", "(49,071)", ""],
        ["Gross profit", "43,879", "40,427", ""],
        ["Diluted earnings per share", "1.64", "1.46", ""],
        ["", "", "", ""],
    ],
)


def test_map_table_normalizes_and_attributes():
    facts = map_table(INCOME_TABLE, DOC)
    by_key = {(f.line_item, f.period.fiscal_year): f for f in facts}

    revenue = by_key[("revenue", 2024)]
    assert revenue.value == Decimal("94930") * 1_000_000  # scale applied
    assert revenue.value_as_reported == Decimal("94930")  # as printed kept
    assert revenue.scale == 1_000_000
    assert revenue.line_item_as_reported == "Net sales"  # company's label kept
    assert revenue.period.quarter == 3
    assert revenue.statement is StatementType.INCOME
    assert revenue.authority is SourceAuthority.QUARTERLY_FILING
    # Cell-level provenance: row 1, col 1 of table 2 on page 4.
    assert (revenue.cell.table_index, revenue.cell.row, revenue.cell.col,
            revenue.cell.page) == (2, 1, 1, 4)

    cost = by_key[("cost_of_revenue", 2024)]
    assert cost.value == Decimal("-51051") * 1_000_000  # parens = negative

    eps = by_key[("eps_diluted", 2024)]
    assert eps.value == Decimal("1.64")  # per-share rows are never scaled
    assert eps.scale == 1

    # The "% Change" column resolves no period -> contributes no facts.
    assert all(f.cell.col != 3 for f in facts)
    # Both period columns mapped.
    assert ("revenue", 2023) in by_key


def test_unmapped_labels_keep_as_reported_identity():
    table = ParsedTable(
        index=0,
        caption="(In millions)",
        rows=[
            ["", "Three Months Ended September 30, 2024"],
            ["Deferred widget credits", "412"],
        ],
    )
    (fact,) = map_table(table, DOC)
    assert fact.line_item is None
    assert fact.line_item_as_reported == "Deferred widget credits"
    assert fact.value == Decimal("412000000")


def test_non_gaap_label_tagging():
    table = ParsedTable(
        index=0,
        caption="(In millions)",
        rows=[
            ["", "Three Months Ended September 30, 2024"],
            ["Adjusted operating income", "30,500"],
        ],
    )
    (fact,) = map_table(table, DOC)
    assert fact.basis is Basis.NON_GAAP


def test_scale_carries_forward_to_captionless_tables():
    first = ParsedTable(
        index=0, caption="(In millions)",
        rows=[["", "FY2024"], ["Net sales", "391,035"]],
    )
    continuation = ParsedTable(
        index=1, caption="",
        rows=[["", "FY2024"], ["Total assets", "364,980"]],
    )
    facts = map_document_tables([first, continuation], DOC)
    assets = next(f for f in facts if f.line_item == "total_assets")
    assert assets.value == Decimal("364980") * 1_000_000


def test_table_without_period_headers_yields_nothing():
    table = ParsedTable(
        index=0, caption="(In millions)",
        rows=[["Item", "Amount"], ["Net sales", "94,930"]],
    )
    assert map_table(table, DOC) == []
