"""TextractParser: block-graph mapping verified against a mocked response —
no AWS account or network involved."""

from __future__ import annotations

from typing import Any

import pytest
from app.core.models import DocRef
from app.extraction.textract import TextractParser, parse_blocks


def _geom(top: float, height: float = 0.02) -> dict[str, Any]:
    return {"Geometry": {"BoundingBox": {"Top": top, "Height": height, "Left": 0.1, "Width": 0.8}}}


def _word(wid: str, text: str, top: float) -> dict[str, Any]:
    return {"Id": wid, "BlockType": "WORD", "Text": text, **_geom(top)}


def _line(lid: str, text: str, top: float) -> dict[str, Any]:
    return {"Id": lid, "BlockType": "LINE", "Text": text, "Page": 1, **_geom(top)}


def _cell(cid: str, row: int, col: int, word_ids: list[str], top: float) -> dict[str, Any]:
    rel = [{"Type": "CHILD", "Ids": word_ids}] if word_ids else []
    return {
        "Id": cid, "BlockType": "CELL", "RowIndex": row, "ColumnIndex": col,
        "Relationships": rel, **_geom(top),
    }


BLOCKS: list[dict[str, Any]] = [
    {"Id": "page1", "BlockType": "PAGE", "Page": 1, **_geom(0.0, 1.0)},
    _line("l1", "CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS", 0.10),
    _line("l2", "(In millions)", 0.13),
    # Table from 0.20 to 0.50; the LINE inside it must not leak into prose.
    {
        "Id": "t1", "BlockType": "TABLE", "Page": 1,
        "Relationships": [{"Type": "CHILD", "Ids": ["c11", "c12", "c21", "c22"]}],
        **_geom(0.20, 0.30),
    },
    _cell("c11", 1, 1, [], 0.21),
    _cell("c12", 1, 2, ["w1", "w2", "w3", "w4", "w5"], 0.21),
    _cell("c21", 2, 1, ["w6", "w7"], 0.25),
    _cell("c22", 2, 2, ["w8", "w9"], 0.25),
    _word("w1", "Three", 0.21), _word("w2", "Months", 0.21),
    _word("w3", "Ended", 0.21), _word("w4", "September 30,", 0.21),
    _word("w5", "2024", 0.21),
    _word("w6", "Net", 0.25), _word("w7", "sales", 0.25),
    _word("w8", "$", 0.25), _word("w9", "94,930", 0.25),
    _line("l3", "Net sales", 0.25),  # inside the table bbox
    _line("l4", "Forward-looking statements follow.", 0.60),
]


def ref(filetype: str = "pdf") -> DocRef:
    return DocRef(doc_id="acme_10q.pdf", source_url="s3://x", filetype=filetype)


def test_blocks_become_table_with_caption_and_grid():
    doc = parse_blocks(ref(), BLOCKS)

    (table,) = doc.tables
    assert table.rows == [
        ["", "Three Months Ended September 30, 2024"],
        ["Net sales", "$ 94,930"],
    ]
    assert "STATEMENTS OF OPERATIONS" in table.caption
    assert "In millions" in table.caption
    assert table.page == 1


def test_prose_excludes_in_table_lines():
    doc = parse_blocks(ref(), BLOCKS)
    assert "Forward-looking statements follow." in doc.text
    assert "Net sales" not in doc.text


def test_textract_table_feeds_the_fact_mapper():
    """The adapter's output plugs straight into the existing pipeline."""
    from datetime import date
    from decimal import Decimal

    from app.core.finance import FinancialDocMeta, SourceAuthority

    from ingestion.pipeline.facts import map_table

    doc = parse_blocks(ref(), BLOCKS)
    meta = FinancialDocMeta(
        doc_id="acme_10q.pdf", entity_id="ACME", doc_type="10-Q",
        authority=SourceAuthority.QUARTERLY_FILING, filed_date=date(2024, 10, 30),
    )
    (fact,) = map_table(doc.tables[0], meta)
    assert fact.line_item == "revenue"
    assert fact.value == Decimal("94930") * 1_000_000  # caption scale applied


async def test_parse_calls_analyze_document_with_tables_feature():
    captured: dict[str, Any] = {}

    class FakeClient:
        def analyze_document(self, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"Blocks": BLOCKS}

    parser = TextractParser(region="us-east-1", client=FakeClient())
    doc = await parser.parse(ref(), b"%PDF-1.7")

    assert captured["FeatureTypes"] == ["TABLES"]
    assert captured["Document"] == {"Bytes": b"%PDF-1.7"}
    assert len(doc.tables) == 1


async def test_html_filetype_is_rejected():
    parser = TextractParser(region="us-east-1", client=object())
    with pytest.raises(ValueError, match="html parser"):
        await parser.parse(ref("html"), b"<html/>")
