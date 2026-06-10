"""Built-in FinancialParser for native-HTML filings (SEC EDGAR 10-K/10-Q).

Extracts <table> elements as cell grids and associates each with a caption —
the nearest preceding heading plus any short text between it and the table —
because that's where filings declare scale and currency ("(In millions, except
per share amounts)"). Narrative text (tables removed) feeds the existing RAG
chunking path.

Known v1 limitations (the commercial-parser adapter is the answer for these):
- colspan/rowspan are not expanded; complex merged-header tables may misalign,
- scanned/image PDFs and DOCX are rejected rather than mis-parsed,
- split currency cells ("$" in its own <td>) yield a symbol-only cell that
  parses as no value.
"""

from __future__ import annotations

import os

from bs4 import BeautifulSoup, Tag

from app.core.finance import ParsedFinancialDoc, ParsedTable
from app.core.models import DocRef

_SUPPORTED = {"html", "htm"}
_TEXT_ONLY = {"txt", "md"}
_CAPTION_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "b", "strong"}


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _caption_for(table: Tag) -> str:
    """The table's own <caption>, else nearby preceding heading/short text."""
    if table.caption:
        text = table.caption.get_text(" ", strip=True)
        if text:
            return text

    parts: list[str] = []
    for el in table.previous_elements:
        if isinstance(el, Tag) and el.name == "table":
            break  # don't inherit another table's caption
        if isinstance(el, Tag) and el.name in _CAPTION_TAGS:
            text = el.get_text(" ", strip=True)
            if text:
                parts.append(text)
                if el.name.startswith("h"):
                    break  # the heading completes the caption
        if len(parts) >= 3:
            break
    return " ".join(reversed(parts))


def _table_rows(table: Tag) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if cells:
            rows.append([c.get_text(" ", strip=True) for c in cells])
    return rows


class HtmlTableParser:
    name = "html"

    async def parse(self, ref: DocRef, content: bytes) -> ParsedFinancialDoc:
        if ref.filetype in _TEXT_ONLY:
            text = _decode(content)
            title = os.path.splitext(os.path.basename(ref.doc_id))[0]
            return ParsedFinancialDoc(ref=ref, title=title, text=text, tables=[])
        if ref.filetype not in _SUPPORTED:
            raise ValueError(
                f"HtmlTableParser cannot parse '{ref.filetype}' documents; "
                "configure a commercial financial parser for PDFs/scans."
            )

        html = _decode(content)
        soup = BeautifulSoup(html, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        if not title and soup.h1:
            title = soup.h1.get_text(strip=True)
        if not title:
            title = os.path.splitext(os.path.basename(ref.doc_id))[0].replace("_", " ")

        tables = [
            ParsedTable(index=i, rows=_table_rows(t), caption=_caption_for(t))
            for i, t in enumerate(soup.find_all("table"))
            if _table_rows(t)
        ]

        # Narrative text = the document with tables removed (parsed fresh so
        # caption association above is unaffected).
        prose_soup = BeautifulSoup(html, "lxml")
        for tag in prose_soup(["script", "style", "noscript", "table"]):
            tag.decompose()
        text = prose_soup.get_text(separator="\n")

        return ParsedFinancialDoc(ref=ref, title=title, text=text, tables=tables)
