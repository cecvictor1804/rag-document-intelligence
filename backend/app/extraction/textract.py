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

    def __init__(
        self,
        region: str,
        client: Any | None = None,
        s3_client: Any | None = None,
        async_bucket: str = "",
        max_pages: int = 50,
        poll_interval: float = 2.0,
        max_wait: float = 600.0,
    ) -> None:
        """`client`/`s3_client` are injectable for tests; lazily built from
        boto3 otherwise. With `async_bucket` set, parsing uses the S3-based
        async API (multi-page PDFs); otherwise sync inline bytes (single-page).
        `max_pages` is a cost flag: documents over it are logged loudly."""
        self._region = region
        self._client = client
        self._s3 = s3_client
        self.async_bucket = async_bucket
        self.max_pages = max_pages
        self.poll_interval = poll_interval
        self.max_wait = max_wait

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("textract", region_name=self._region)
        return self._client

    def _get_s3(self) -> Any:
        if self._s3 is None:
            import boto3

            self._s3 = boto3.client("s3", region_name=self._region)
        return self._s3

    async def parse(self, ref: DocRef, content: bytes) -> ParsedFinancialDoc:
        if ref.filetype not in _SUPPORTED:
            raise ValueError(
                f"TextractParser handles {sorted(_SUPPORTED)} documents, "
                f"not '{ref.filetype}' (use the html parser for HTML filings)."
            )
        if self.async_bucket:
            blocks = await self._analyze_async(ref, content)
        else:
            client = self._get_client()
            response = await asyncio.to_thread(
                client.analyze_document,
                Document={"Bytes": content},
                FeatureTypes=["TABLES"],
            )
            blocks = response["Blocks"]
        return parse_blocks(ref, blocks)

    async def _analyze_async(self, ref: DocRef, content: bytes) -> list[dict[str, Any]]:
        """S3-based StartDocumentAnalysis for multi-page documents: upload →
        start → poll (backoff) → aggregate every NextToken page → clean up."""
        import logging
        import uuid

        logger = logging.getLogger("rag.textract")
        client = self._get_client()
        s3 = self._get_s3()
        key = f"textract-tmp/{uuid.uuid4()}.{ref.filetype}"

        await asyncio.to_thread(
            s3.put_object, Bucket=self.async_bucket, Key=key, Body=content
        )
        try:
            start = await asyncio.to_thread(
                client.start_document_analysis,
                DocumentLocation={
                    "S3Object": {"Bucket": self.async_bucket, "Name": key}
                },
                FeatureTypes=["TABLES"],
            )
            job_id = start["JobId"]

            waited = 0.0
            while True:
                response = await asyncio.to_thread(
                    client.get_document_analysis, JobId=job_id
                )
                status = response["JobStatus"]
                if status == "SUCCEEDED":
                    break
                if status == "FAILED":
                    raise RuntimeError(
                        f"Textract job failed: {response.get('StatusMessage', '')}"
                    )
                if waited >= self.max_wait:
                    raise TimeoutError(f"Textract job {job_id} exceeded max wait")
                await asyncio.sleep(self.poll_interval)
                waited += self.poll_interval

            pages = response.get("DocumentMetadata", {}).get("Pages", 0)
            if pages > self.max_pages:
                logger.warning(
                    "textract: %s is %d pages (cap %d) — per-page cost flag",
                    ref.doc_id, pages, self.max_pages,
                )

            blocks: list[dict[str, Any]] = list(response.get("Blocks", []))
            token = response.get("NextToken")
            while token:
                page = await asyncio.to_thread(
                    client.get_document_analysis, JobId=job_id, NextToken=token
                )
                blocks.extend(page.get("Blocks", []))
                token = page.get("NextToken")
            return blocks
        finally:
            try:
                await asyncio.to_thread(
                    s3.delete_object, Bucket=self.async_bucket, Key=key
                )
            except Exception:  # noqa: BLE001 — cleanup must not mask the result
                logger.warning("textract: temp object cleanup failed for %s", key)
