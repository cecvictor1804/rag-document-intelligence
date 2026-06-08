"""Markdown loader: keeps heading text (useful for sectioning) but strips the
most disruptive markup. Title is the first H1, falling back to the filename.
"""

from __future__ import annotations

import os
import re

from ingestion.pipeline.loaders.text import _decode

_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def load(data: bytes, filename: str) -> tuple[str, str]:
    raw = _decode(data)

    m = _H1.search(raw)
    title = (
        m.group(1).strip()
        if m
        else os.path.splitext(os.path.basename(filename))[0].replace("_", " ").strip()
    )

    text = _CODE_FENCE.sub(" ", raw)
    text = _IMAGE.sub(" ", text)
    text = _LINK.sub(r"\1", text)  # keep link text, drop the URL
    return title or os.path.basename(filename), text
