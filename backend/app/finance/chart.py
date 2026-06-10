"""Canonical chart of accounts — the curated line-item taxonomy.

A deliberately small, high-value subset of US-GAAP concepts (the `gaap` field
names the closest us-gaap taxonomy concept for future XBRL alignment). Mapping
is conservative: an as-reported label maps to a canonical item only on an exact
normalized-synonym match — a wrong mapping is worse than no mapping, because the
as-reported label is always preserved on the fact either way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.finance import StatementType


@dataclass(frozen=True, slots=True)
class LineItem:
    canonical: str
    statement: StatementType
    gaap: str  # closest us-gaap concept (reference / future XBRL alignment)
    synonyms: tuple[str, ...]  # normalized as-reported labels that mean this
    unit: str = "currency"


_I = StatementType.INCOME
_B = StatementType.BALANCE
_C = StatementType.CASH_FLOW

CHART: tuple[LineItem, ...] = (
    # ── Income statement ─────────────────────────────────────────────────
    LineItem("revenue", _I, "Revenues", (
        "revenue", "revenues", "net revenue", "net revenues", "total revenue",
        "total revenues", "net sales", "total net sales", "sales",
        "revenue net", "total net revenues",
    )),
    LineItem("cost_of_revenue", _I, "CostOfRevenue", (
        "cost of revenue", "cost of revenues", "cost of sales",
        "cost of goods sold", "cost of products sold", "total cost of revenue",
        "total cost of sales",
    )),
    LineItem("gross_profit", _I, "GrossProfit", (
        "gross profit", "gross margin", "gross income",
    )),
    LineItem("research_development", _I, "ResearchAndDevelopmentExpense", (
        "research and development", "research and development expense",
        "research and development expenses", "r and d",
    )),
    LineItem("selling_general_admin", _I, "SellingGeneralAndAdministrativeExpense", (
        "selling general and administrative",
        "selling general and administrative expenses",
        "general and administrative", "sales and marketing",
    )),
    LineItem("operating_expenses", _I, "OperatingExpenses", (
        "operating expenses", "total operating expenses",
    )),
    LineItem("operating_income", _I, "OperatingIncomeLoss", (
        "operating income", "operating income loss", "income from operations",
        "operating profit", "loss from operations", "operating loss",
    )),
    LineItem("income_tax_expense", _I, "IncomeTaxExpenseBenefit", (
        "income tax expense", "provision for income taxes",
        "income tax provision", "provision for taxes",
    )),
    LineItem("net_income", _I, "NetIncomeLoss", (
        "net income", "net income loss", "net earnings", "net loss",
        "net income attributable to common stockholders",
    )),
    LineItem("eps_diluted", _I, "EarningsPerShareDiluted", (
        "diluted earnings per share", "earnings per share diluted", "diluted eps",
        "diluted net income per share", "diluted",
    ), unit="per_share"),
    LineItem("eps_basic", _I, "EarningsPerShareBasic", (
        "basic earnings per share", "earnings per share basic", "basic eps",
        "basic net income per share", "basic",
    ), unit="per_share"),
    # ── Balance sheet ────────────────────────────────────────────────────
    LineItem("cash_and_equivalents", _B, "CashAndCashEquivalentsAtCarryingValue", (
        "cash and cash equivalents", "cash and equivalents",
        "cash cash equivalents and restricted cash",
    )),
    LineItem("accounts_receivable", _B, "AccountsReceivableNetCurrent", (
        "accounts receivable", "accounts receivable net", "receivables",
        "trade receivables",
    )),
    LineItem("inventory", _B, "InventoryNet", (
        "inventory", "inventories", "inventories net",
    )),
    LineItem("total_current_assets", _B, "AssetsCurrent", (
        "total current assets", "current assets",
    )),
    LineItem("total_assets", _B, "Assets", (
        "total assets",
    )),
    LineItem("accounts_payable", _B, "AccountsPayableCurrent", (
        "accounts payable",
    )),
    LineItem("total_current_liabilities", _B, "LiabilitiesCurrent", (
        "total current liabilities", "current liabilities",
    )),
    LineItem("long_term_debt", _B, "LongTermDebtNoncurrent", (
        "long term debt", "long term debt net", "long term borrowings",
        "term debt",
    )),
    LineItem("total_liabilities", _B, "Liabilities", (
        "total liabilities",
    )),
    LineItem("total_equity", _B, "StockholdersEquity", (
        "total stockholders equity", "total shareholders equity",
        "stockholders equity", "shareholders equity", "total equity",
        "total stockholders deficit",
    )),
    # ── Cash flow ────────────────────────────────────────────────────────
    LineItem("operating_cash_flow", _C, "NetCashProvidedByUsedInOperatingActivities", (
        "net cash provided by operating activities",
        "net cash provided by used in operating activities",
        "cash generated by operating activities",
        "net cash from operating activities", "cash flow from operations",
    )),
    LineItem("capital_expenditures", _C, "PaymentsToAcquirePropertyPlantAndEquipment", (
        "capital expenditures", "purchases of property and equipment",
        "payments for acquisition of property plant and equipment",
        "purchases of property plant and equipment", "additions to property and equipment",
    )),
)

_BY_CANONICAL: dict[str, LineItem] = {li.canonical: li for li in CHART}
_BY_SYNONYM: dict[str, LineItem] = {
    syn: li for li in CHART for syn in li.synonyms
}

_NORMALIZE_RE = re.compile(r"[^a-z0-9 ]+")
_WS_RE = re.compile(r"\s+")
# Trailing footnote markers on labels: "Total revenue (1)" / "Net sales*"
_FOOTNOTE_RE = re.compile(r"(\(\d+\)|\*+)\s*$")


def normalize_label(label: str) -> str:
    """Lowercase, strip footnote markers/punctuation, collapse whitespace."""
    s = _FOOTNOTE_RE.sub("", label.strip().lower())
    s = _NORMALIZE_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def map_line_item(as_reported: str) -> LineItem | None:
    """Canonical concept for an as-reported label, or None (exact-synonym only)."""
    return _BY_SYNONYM.get(normalize_label(as_reported))


def line_item(canonical: str) -> LineItem | None:
    return _BY_CANONICAL.get(canonical)


def canonical_names() -> list[str]:
    return [li.canonical for li in CHART]
