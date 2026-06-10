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
from app.extraction.textract import TextractParser


def build_financial_parser(settings: Settings) -> FinancialParser:
    if settings.financial_parser == "html":
        return HtmlTableParser()
    if settings.financial_parser == "textract":
        return TextractParser(
            region=settings.aws_region,
            async_bucket=settings.textract_async_bucket,
            max_pages=settings.textract_max_pages,
        )
    raise ValueError(f"unknown financial parser: {settings.financial_parser}")
