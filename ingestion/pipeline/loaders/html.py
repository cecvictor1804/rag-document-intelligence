"""HTML loader using BeautifulSoup. Strips scripts/styles, extracts visible
text, and prefers <title> then <h1> then the filename for the title.
"""

from __future__ import annotations

import os

from bs4 import BeautifulSoup

from ingestion.pipeline.loaders.text import _decode


def load(data: bytes, filename: str) -> tuple[str, str]:
    soup = BeautifulSoup(_decode(data), "lxml")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    if not title and soup.h1:
        title = soup.h1.get_text(strip=True)
    if not title:
        title = os.path.splitext(os.path.basename(filename))[0].replace("_", " ")

    text = soup.get_text(separator="\n")
    return title or os.path.basename(filename), text
