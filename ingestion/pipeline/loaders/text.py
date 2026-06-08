"""Plain-text loader."""

from __future__ import annotations

import os


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def load(data: bytes, filename: str) -> tuple[str, str]:
    text = _decode(data)
    title = os.path.splitext(os.path.basename(filename))[0].replace("_", " ").strip()
    return title or os.path.basename(filename), text
