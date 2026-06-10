"""Financial domain DTOs (Phase 5).

Like `core.models`, these are plain dataclasses shared by ingestion (the fact
mapper), the metric store, and the compute layer. Money is `Decimal` end to end —
floats never touch a reported figure.

Key modeling decisions (from the Phase 5 design):
- Every fact keeps BOTH the normalized base-unit value (`value`, e.g. dollars)
  and the as-reported one (`value_as_reported`, e.g. "4,200" in millions), plus
  the detected `scale`/`currency`, so nothing is lost in normalization.
- Line items are hybrid: `line_item` is the canonical concept (None when
  unmapped); `line_item_as_reported` is always the company's own label.
- `CellRef` is the cell-level provenance every downstream citation points at.
- `SourceAuthority` + filing date implement the conflict-precedence hierarchy
  (audited filing > amendment logic handled via recency among same-rank docs;
  press release lowest).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import IntEnum, StrEnum

from app.core.models import DocRef


class StatementType(StrEnum):
    INCOME = "income"
    BALANCE = "balance"
    CASH_FLOW = "cash_flow"
    OTHER = "other"


class Basis(StrEnum):
    GAAP = "gaap"
    NON_GAAP = "non_gaap"


class SourceAuthority(IntEnum):
    """Precedence rank when sources disagree on the same fact. Higher wins;
    ties broken by filing recency (so a 10-K/A restatement beats the 10-K)."""

    OTHER = 0
    PRESS_RELEASE = 1
    QUARTERLY_FILING = 2  # 10-Q
    ANNUAL_FILING = 3  # 10-K (audited)
    AMENDMENT = 4  # 10-K/A, 10-Q/A


@dataclass(slots=True, frozen=True)
class FiscalPeriod:
    """A fiscal year or quarter. `quarter is None` means the full year."""

    fiscal_year: int
    quarter: int | None = None  # 1..4, or None for FY
    end_date: date | None = None

    @property
    def label(self) -> str:
        if self.quarter is None:
            return f"FY{self.fiscal_year}"
        return f"Q{self.quarter} FY{self.fiscal_year}"

    @property
    def is_annual(self) -> bool:
        return self.quarter is None


@dataclass(slots=True, frozen=True)
class CellRef:
    """Cell-level provenance: exactly where a figure came from."""

    table_index: int  # nth table in the document
    row: int
    col: int
    page: int | None = None


@dataclass(slots=True)
class FinancialFact:
    """One reported figure, normalized, with full provenance."""

    entity_id: str
    doc_id: str
    statement: StatementType
    line_item_as_reported: str  # the company's own label, always kept
    period: FiscalPeriod
    value: Decimal  # normalized to base units (e.g. dollars, shares)
    value_as_reported: Decimal  # the number as printed
    scale: int = 1  # 1 | 1_000 | 1_000_000 | 1_000_000_000
    currency: str = "USD"
    unit: str = "currency"  # currency | shares | per_share | percent | ratio
    line_item: str | None = None  # canonical concept (chart.py); None = unmapped
    basis: Basis = Basis.GAAP
    segment: str | None = None  # None == consolidated
    authority: SourceAuthority = SourceAuthority.OTHER
    cell: CellRef | None = None
    fact_id: int | None = None  # DB id, populated on read


@dataclass(slots=True)
class FinancialDocMeta:
    """Document-level metadata for the precedence/restatement model."""

    doc_id: str
    entity_id: str
    doc_type: str  # "10-K" | "10-Q" | "10-K/A" | "press_release" | ...
    authority: SourceAuthority
    filed_date: date | None = None
    amends_doc_id: str | None = None
    source_url: str = ""


@dataclass(slots=True)
class ParsedTable:
    """A table as returned by a FinancialParser: raw cell grid + the caption /
    nearby text that carries scale and currency context ("(in millions)")."""

    index: int  # nth table in the document
    rows: list[list[str]]
    caption: str = ""
    page: int | None = None


@dataclass(slots=True)
class ParsedFinancialDoc:
    """FinancialParser output: narrative text (feeds the existing RAG path)
    plus structured tables (feeds the fact mapper)."""

    ref: DocRef
    title: str
    text: str
    tables: list[ParsedTable] = field(default_factory=list)


@dataclass(slots=True)
class MetricResult:
    """A deterministically computed metric, carrying the exact source facts so
    every figure in an answer can cite its cells."""

    metric: str
    value: Decimal
    unit: str  # "percent" | "ratio" | "currency" | ...
    period: FiscalPeriod
    formula: str  # human-readable, e.g. "gross_profit / revenue"
    inputs: list[FinancialFact]
    currency: str | None = None


@dataclass(slots=True)
class ReconciliationIssue:
    """An ingest-time invariant violation (extraction distrust signal)."""

    doc_id: str
    check: str  # e.g. "balance_identity", "gross_profit"
    detail: str
    expected: Decimal | None = None
    actual: Decimal | None = None
