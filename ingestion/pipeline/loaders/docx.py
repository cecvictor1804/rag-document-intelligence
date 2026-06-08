"""DOCX loader using python-docx. Joins paragraph text; title is the document's
core-properties title if set, else the first non-empty paragraph, else filename.
"""

from __future__ import annotations

import io
import os

from docx import Document


def load(data: bytes, filename: str) -> tuple[str, str]:
    document = Document(io.BytesIO(data))

    paragraphs = [p.text for p in document.paragraphs if p.text and p.text.strip()]
    text = "\n".join(paragraphs)

    title = ""
    try:
        if document.core_properties.title:
            title = document.core_properties.title.strip()
    except Exception:  # noqa: BLE001
        pass
    if not title and paragraphs:
        title = paragraphs[0][:120].strip()
    if not title:
        title = os.path.splitext(os.path.basename(filename))[0].replace("_", " ").strip()

    return title or os.path.basename(filename), text
