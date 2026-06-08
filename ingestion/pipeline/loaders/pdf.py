"""PDF loader using pypdf. Concatenates page text; title comes from the PDF
metadata if present, otherwise the filename.
"""

from __future__ import annotations

import io
import os

from pypdf import PdfReader


def load(data: bytes, filename: str) -> tuple[str, str]:
    reader = PdfReader(io.BytesIO(data))

    title = ""
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title).strip()
    if not title:
        title = os.path.splitext(os.path.basename(filename))[0].replace("_", " ").strip()

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001 — one bad page shouldn't fail the doc
            continue
    return title or os.path.basename(filename), "\n\n".join(pages)
