"""Per-filetype loaders. Each `load(data, filename) -> (title, text)` extracts
plain text and a best-effort title. `load_document` dispatches by filetype.
"""

from __future__ import annotations

from collections.abc import Callable

from ingestion.pipeline.loaders import docx, html, markdown, pdf, text

# filetype -> loader function
_REGISTRY: dict[str, Callable[[bytes, str], tuple[str, str]]] = {
    "pdf": pdf.load,
    "docx": docx.load,
    "html": html.load,
    "htm": html.load,
    "md": markdown.load,
    "markdown": markdown.load,
    "txt": text.load,
    "text": text.load,
}

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".md", ".markdown", ".txt"}


class UnsupportedFiletype(ValueError):
    pass


def filetype_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {"htm": "html", "markdown": "md", "text": "txt"}.get(ext, ext)


def load_document(data: bytes, filename: str) -> tuple[str, str]:
    """Return (title, text). Raises UnsupportedFiletype for unknown extensions."""
    ftype = filetype_for(filename)
    loader = _REGISTRY.get(ftype)
    if loader is None:
        raise UnsupportedFiletype(filename)
    return loader(data, filename)
