"""Text normalization applied after extraction and before chunking.

Conservative on purpose: collapse runaway whitespace and normalize newlines
without destroying paragraph/section boundaries (the chunker relies on them).
"""

from __future__ import annotations

import re

_TRAILING_WS = re.compile(r"[ \t]+(\n)")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")
_MANY_SPACES = re.compile(r"[ \t]{2,}")


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_WS.sub(r"\1", text)
    text = _MANY_SPACES.sub(" ", text)
    text = _MANY_BLANK_LINES.sub("\n\n", text)
    return text.strip()
