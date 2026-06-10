"""HtmlTableParser: tables with captions out, narrative text separate."""

from __future__ import annotations

import pytest
from app.core.models import DocRef
from app.extraction.html_table import HtmlTableParser

HTML = b"""
<html><head><title>Acme 10-Q</title></head><body>
<p>Management discussion narrative goes here.</p>
<h2>CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS</h2>
<p>(In millions, except per share amounts)</p>
<table>
  <tr><th></th><th>Three Months Ended September 30, 2024</th></tr>
  <tr><td>Net sales</td><td>$ 94,930</td></tr>
</table>
<h2>CONDENSED CONSOLIDATED BALANCE SHEETS</h2>
<p>(In millions)</p>
<table>
  <tr><th></th><th>September 30, 2024</th></tr>
  <tr><td>Total assets</td><td>364,980</td></tr>
</table>
</body></html>
"""


def ref(filetype: str = "html") -> DocRef:
    return DocRef(doc_id="acme_10q.html", source_url="file:///x", filetype=filetype)


async def test_tables_extracted_with_their_own_captions():
    doc = await HtmlTableParser().parse(ref(), HTML)

    assert doc.title == "Acme 10-Q"
    assert len(doc.tables) == 2

    income, balance = doc.tables
    assert "STATEMENTS OF OPERATIONS" in income.caption
    assert "In millions" in income.caption
    assert income.rows[1] == ["Net sales", "$ 94,930"]

    # The second table must NOT inherit the first table's caption.
    assert "BALANCE SHEETS" in balance.caption
    assert "OPERATIONS" not in balance.caption
    assert balance.index == 1


async def test_narrative_text_excludes_table_cells():
    doc = await HtmlTableParser().parse(ref(), HTML)
    assert "Management discussion narrative" in doc.text
    assert "94,930" not in doc.text


async def test_text_only_filetypes_yield_no_tables():
    doc = await HtmlTableParser().parse(ref("txt"), b"plain narrative")
    assert doc.tables == []
    assert doc.text == "plain narrative"


async def test_unsupported_filetypes_are_rejected_not_misparsed():
    with pytest.raises(ValueError, match="commercial"):
        await HtmlTableParser().parse(ref("pdf"), b"%PDF-1.7 ...")
