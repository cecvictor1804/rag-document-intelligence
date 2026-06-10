"""AWS Textract FinancialParser — the commercial path for PDFs and scans.

Why Textract as the v1 commercial parser: the deployment is already AWS
(Phase 4), so documents never leave the account (data residency), auth is IAM
roles rather than another vendor API key, and boto3 is already a dependency.
The FinancialParser Protocol keeps it swappable if a specialist vendor
(e.g. better merged-header handling) proves more accurate later.

Mapping: Textract block graph → ParsedFinancialDoc. TABLE blocks become cell
grids via their CELL children (RowIndex/ColumnIndex); LINE blocks above each
table on the same page provide the caption (where scale/currency live); LINE
blocks outside all tables become the narrative text.

Operational notes:
- Synchronous AnalyzeDocument with inline bytes: single-page PDFs and images
  up to the API's size limits. Multi-page PDFs need the async S3-based API
  (start_document_analysis) — planned for the worker integration (5d).
- Cost is per page analyzed; TABLES analysis is the priced feature used here.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.finance import ParsedFinancialDoc, ParsedTable
from app.core.models import DocRef

_SUPPORTED = {"pdf", "png", "jpg", "jpeg", "tiff"}


def _text_for(block: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str:
    """Concatenated WORD/SELECTION child text of a CELL block."""
    words: list[str] = []
    for rel in block.get("Relationships", []):
        if rel["Type"] != "CHILD":
            continue
        for child_id in rel["Ids"]:
            child = by_id.get(child_id)
            if not child:
                continue
            if child["BlockType"] == "WORD":
                words.append(child.get("Text", ""))
            elif child["BlockType"] == "SELECTION_ELEMENT":
                if child.get("SelectionStatus") == "SELECTED":
                    words.append("[x]")
    return " ".join(w for w in words if w)


def _top(block: dict[str, Any]) -> float:
    return float(block["Geometry"]["BoundingBox"]["Top"])


def _bottom(block: dict[str, Any]) -> float:
    bbox = block["Geometry"]["BoundingBox"]
    return float(bbox["Top"]) + float(bbox["Height"])


def parse_blocks(ref: DocRef, blocks: list[dict[str, Any]]) -> ParsedFinancialDoc:
    """Pure mapping from a Textract Blocks list — unit-testable without AWS."""
    by_id = {b["Id"]: b for b in blocks}
    tables = [b for b in blocks if b["BlockType"] == "TABLE"]
    lines = [b for b in blocks if b["BlockType"] == "LINE"]

    def in_any_table(line: dict[str, Any]) -> bool:
        for t in tables:
            if t.get("Page", 1) != line.get("Page", 1):
                continue
            if _top(t) - 0.005 <= _top(line) <= _bottom(t) + 0.005:
                return True
        return False

    parsed_tables: list[ParsedTable] = []
    for index, table in enumerate(tables):
        cells: dict[tuple[int, int], str] = {}
        max_row = max_col = 0
        for rel in table.get("Relationships", []):
            if rel["Type"] != "CHILD":
                continue
            for cell_id in rel["Ids"]:
                cell = by_id.get(cell_id)
                if not cell or cell["BlockType"] != "CELL":
                    continue
                r, c = cell["RowIndex"], cell["ColumnIndex"]
                cells[(r, c)] = _text_for(cell, by_id)
                max_row, max_col = max(max_row, r), max(max_col, c)
        rows = [
            [cells.get((r, c), "") for c in range(1, max_col + 1)]
            for r in range(1, max_row + 1)
        ]

        # Caption: the last few text lines above the table on its page.
        page = table.get("Page", 1)
        above = sorted(
            (
                ln for ln in lines
                if ln.get("Page", 1) == page
                and _bottom(ln) <= _top(table) + 0.001
                and not in_any_table(ln)
            ),
            key=_top,
        )
        caption = " ".join(ln.get("Text", "") for ln in above[-3:])

        parsed_tables.append(
            ParsedTable(index=index, rows=rows, caption=caption, page=page)
        )

    prose = "\n".join(
        ln.get("Text", "")
        for ln in sorted(lines, key=lambda b: (b.get("Page", 1), _top(b)))
        if not in_any_table(ln)
    )
    title = next((ln.get("Text", "") for ln in lines), ref.doc_id)

    return ParsedFinancialDoc(ref=ref, title=title, text=prose, tables=parsed_tables)


class TextractParser:
    name = "textract"

    def __init__(self, region: str, client: Any | None = None) -> None:
        """`client` is injectable for tests; lazily built from boto3 otherwise."""
        self._region = region
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("textract", region_name=self._region)
        return self._client

    async def parse(self, ref: DocRef, content: bytes) -> ParsedFinancialDoc:
        if ref.filetype not in _SUPPORTED:
            raise ValueError(
                f"TextractParser handles {sorted(_SUPPORTED)} documents, "
                f"not '{ref.filetype}' (use the html parser for HTML filings)."
            )
        client = self._get_client()
        response = await asyncio.to_thread(
            client.analyze_document,
            Document={"Bytes": content},
            FeatureTypes=["TABLES"],
        )
        return parse_blocks(ref, response["Blocks"])
