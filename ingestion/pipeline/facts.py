"""Fact mapper: parsed tables → normalized FinancialFacts (Phase 5a).

Takes the structured tables a FinancialParser emits and produces facts with:
- numeric values parsed exactly (Decimal; parentheses = negative; dashes = absent),
- table-level scale ("(in millions)") and currency detected from the caption and
  applied to a normalized base-unit value (the as-reported number is kept too),
- the company's label always preserved; canonical mapping via the chart of
  accounts (conservative, exact-synonym only),
- fiscal periods resolved from column headers ("Three months ended Sep 30, 2024"),
- GAAP vs non-GAAP tagging from caption/label keywords,
- cell-level provenance (table/row/col/page) on every fact.

Pure functions, no I/O — fully unit-testable without a parser vendor.

Known v1 simplification: fiscal periods are calendar-aligned (quarter inferred
from the period-end month). Companies with offset fiscal years (e.g. Apple's
Sep year-end) get calendar labeling until entity fiscal calendars land in 5c.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.finance import (
    Basis,
    CellRef,
    FinancialDocMeta,
    FinancialFact,
    FiscalPeriod,
    ParsedTable,
    StatementType,
)
from app.finance.chart import map_line_item, normalize_label

# ── Numeric cells ────────────────────────────────────────────────────────────

_ABSENT = {"", "-", "--", "—", "–", "n/a", "na", "nm", "*"}
_MONEY_RE = re.compile(
    r"^\(?\s*[$€£¥]?\s*-?\d[\d,]*(?:\.\d+)?\s*\)?%?$"
)


def parse_numeric(cell: str) -> Decimal | None:
    """Parse a table cell to a Decimal, or None when it isn't a number.

    Handles currency symbols, thousands separators, accounting-style
    parentheses for negatives, trailing %, and the various dashes used for
    "no value". Never guesses: anything ambiguous returns None.
    """
    s = cell.strip()
    if s.lower() in _ABSENT:
        return None
    if not _MONEY_RE.match(s):
        return None
    negative = "(" in s and ")" in s
    s = re.sub(r"[($€£¥),%\s]", "", s)
    if not s or s == "-":
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative and value > 0 else value


# ── Table context: scale, currency, statement, basis ─────────────────────────

_SCALES: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"in\s+billions|\$\s*in\s+billions", re.I), 1_000_000_000),
    (re.compile(r"in\s+millions|\$\s*in\s+millions", re.I), 1_000_000),
    (re.compile(r"in\s+thousands|\$\s*in\s+thousands", re.I), 1_000),
)

_CURRENCIES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"€|\bEUR\b"), "EUR"),
    (re.compile(r"£|\bGBP\b"), "GBP"),
    (re.compile(r"¥|\bJPY\b"), "JPY"),
    (re.compile(r"\$|\bUSD\b"), "USD"),
)

_STATEMENTS: tuple[tuple[re.Pattern[str], StatementType], ...] = (
    (re.compile(r"operations|income|earnings", re.I), StatementType.INCOME),
    (re.compile(r"balance\s+sheet|financial\s+position", re.I), StatementType.BALANCE),
    (re.compile(r"cash\s+flow", re.I), StatementType.CASH_FLOW),
)

_NON_GAAP_RE = re.compile(r"non-?gaap|adjusted", re.I)


def detect_scale(caption: str) -> int:
    for pattern, scale in _SCALES:
        if pattern.search(caption):
            return scale
    return 1


def detect_currency(caption: str) -> str:
    for pattern, code in _CURRENCIES:
        if pattern.search(caption):
            return code
    return "USD"


def detect_statement(caption: str) -> StatementType:
    for pattern, statement in _STATEMENTS:
        if pattern.search(caption):
            return statement
    return StatementType.OTHER


def detect_basis(text: str) -> Basis:
    return Basis.NON_GAAP if _NON_GAAP_RE.search(text) else Basis.GAAP


# ── Periods from column headers ──────────────────────────────────────────────

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_DATE_RE = re.compile(
    r"(" + "|".join(_MONTHS) + r")\.?\s+(\d{1,2})\s*,?\s+(\d{4})", re.I
)
_ANNUAL_RE = re.compile(r"twelve\s+months|year\s+ended|fiscal\s+year|annual|fy", re.I)
_QUARTER_RE = re.compile(r"\bQ([1-4])\b|three\s+months|quarter\s+ended", re.I)
_FY_LABEL_RE = re.compile(r"(?:fy|fiscal\s+year)\s*(\d{4})|^(\d{4})$", re.I)


def resolve_period(header: str) -> FiscalPeriod | None:
    """Fiscal period from a column header. None when no period is present
    (e.g. a '% change' column) — such columns are skipped, never guessed."""
    header = header.strip()
    if not header:
        return None

    annual = bool(_ANNUAL_RE.search(header))
    quarterly = _QUARTER_RE.search(header)

    m = _DATE_RE.search(header)
    if m:
        month = _MONTHS[m.group(1).lower().rstrip(".")]
        end = date(int(m.group(3)), month, min(int(m.group(2)), 28))
        if annual and not quarterly:
            return FiscalPeriod(fiscal_year=end.year, quarter=None, end_date=end)
        quarter = (month - 1) // 3 + 1  # calendar-aligned (v1 simplification)
        return FiscalPeriod(fiscal_year=end.year, quarter=quarter, end_date=end)

    if quarterly and quarterly.group(1):
        year_m = re.search(r"(\d{4})", header)
        if year_m:
            return FiscalPeriod(int(year_m.group(1)), int(quarterly.group(1)))
        return None

    fy = _FY_LABEL_RE.search(header)
    if fy:
        year = int(fy.group(1) or fy.group(2))
        if 1900 < year < 2200:
            return FiscalPeriod(fiscal_year=year, quarter=None)
    return None


# ── Table → facts ────────────────────────────────────────────────────────────

def _header_row(table: ParsedTable) -> tuple[int, list[FiscalPeriod | None]] | None:
    """Find the first row whose cells resolve to at least one period; return
    (row_index, per-column periods)."""
    for r, row in enumerate(table.rows[:4]):  # headers live near the top
        periods = [resolve_period(cell) for cell in row]
        if sum(p is not None for p in periods) >= 1:
            return r, periods
    return None


def map_table(
    table: ParsedTable,
    doc: FinancialDocMeta,
    default_scale: int | None = None,
) -> list[FinancialFact]:
    """Map one parsed table to normalized facts.

    Column 0 is the line-item label; the header row assigns a FiscalPeriod to
    each remaining column (period-less columns like '% change' are skipped).
    Rows whose label maps to nothing canonical still produce facts — the
    as-reported label is the identity of last resort.
    """
    header = _header_row(table)
    if header is None:
        return []
    header_idx, periods = header

    scale = detect_scale(table.caption) or 1
    if scale == 1 and default_scale:
        scale = default_scale
    currency = detect_currency(table.caption)
    statement = detect_statement(table.caption)
    table_basis = detect_basis(table.caption)

    facts: list[FinancialFact] = []
    for r in range(header_idx + 1, len(table.rows)):
        row = table.rows[r]
        if not row or not row[0].strip():
            continue
        label = row[0].strip()
        if not normalize_label(label):
            continue
        item = map_line_item(label)
        unit = item.unit if item else "currency"
        # Per-share figures are printed unscaled even in "(in millions)" tables.
        row_scale = 1 if unit == "per_share" else scale
        row_basis = (
            Basis.NON_GAAP if detect_basis(label) is Basis.NON_GAAP else table_basis
        )
        row_statement = item.statement if item else statement

        for c in range(1, len(row)):
            if c >= len(periods) or periods[c] is None:
                continue
            value = parse_numeric(row[c])
            if value is None:
                continue
            period = periods[c]
            assert period is not None
            facts.append(
                FinancialFact(
                    entity_id=doc.entity_id,
                    doc_id=doc.doc_id,
                    statement=row_statement,
                    line_item=item.canonical if item else None,
                    line_item_as_reported=label,
                    period=period,
                    value=value * row_scale,
                    value_as_reported=value,
                    scale=row_scale,
                    currency=currency,
                    unit=unit,
                    basis=row_basis,
                    authority=doc.authority,
                    cell=CellRef(table_index=table.index, row=r, col=c, page=table.page),
                )
            )
    return facts


def map_document_tables(
    tables: list[ParsedTable], doc: FinancialDocMeta
) -> list[FinancialFact]:
    """Map every table in a document. A scale declared by an earlier table's
    caption carries forward as the default for captionless continuation tables."""
    facts: list[FinancialFact] = []
    carried_scale: int | None = None
    for table in tables:
        scale = detect_scale(table.caption)
        if scale != 1:
            carried_scale = scale
        facts.extend(map_table(table, doc, default_scale=carried_scale))
    return facts
