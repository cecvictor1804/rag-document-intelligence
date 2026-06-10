"""Financial document extraction — FinancialParser implementations.

The built-in HTML table parser handles native-HTML filings (SEC EDGAR 10-K/10-Q
are HTML) with zero vendor cost. Scanned PDFs/images need the commercial parser
adapter (pending vendor selection); both sit behind the FinancialParser
Protocol so swapping is a config change.
"""

from __future__ import annotations

from app.config import Settings
from app.core.interfaces import FinancialParser
from app.extraction.html_table import HtmlTableParser


def build_financial_parser(settings: Settings) -> FinancialParser:
    if settings.financial_parser == "html":
        return HtmlTableParser()
    raise ValueError(f"unknown financial parser: {settings.financial_parser}")
