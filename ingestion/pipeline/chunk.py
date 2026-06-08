"""Chunking: split a cleaned document into overlapping, section-aware chunks.

Strategy: pack paragraph blocks greedily up to `chunk_tokens`, then start the
next chunk with a trailing overlap (~`overlap_tokens`) so context isn't lost at
boundaries. Markdown-style headings are tracked and attached as the chunk's
`section`. Token counts are approximate (≈4 chars/token) — good enough for
sizing; the embedding provider does the real tokenization.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def estimate_tokens(text: str) -> int:
    """Cheap, model-agnostic token estimate for chunk sizing only."""
    return max(1, math.ceil(len(text) / 4))


@dataclass(slots=True)
class TextChunk:
    text: str
    section: str | None
    ordinal: int


def _split_blocks(text: str) -> list[tuple[str, str | None]]:
    """Split into (block_text, section) pairs, tracking the current heading."""
    blocks: list[tuple[str, str | None]] = []
    section: str | None = None
    for raw_block in re.split(r"\n\s*\n", text):
        block = raw_block.strip()
        if not block:
            continue
        # A block that is purely a heading updates the section and isn't emitted
        # as body text on its own.
        first_line = block.splitlines()[0]
        m = _HEADING.match(first_line)
        if m and len(block.splitlines()) == 1:
            section = m.group(2).strip()
            continue
        if m:
            section = m.group(2).strip()
        blocks.append((block, section))
    return blocks


def _overlap_tail(text: str, overlap_tokens: int) -> str:
    """Return the trailing portion of `text` approximating `overlap_tokens`."""
    if overlap_tokens <= 0:
        return ""
    words = text.split()
    # ~0.75 words per token (≈4 chars/token, ~5 chars/word incl. space).
    keep_words = max(1, int(overlap_tokens * 0.75))
    return " ".join(words[-keep_words:])


def chunk_text(
    text: str,
    *,
    chunk_tokens: int,
    overlap_tokens: int,
) -> list[TextChunk]:
    blocks = _split_blocks(text)
    if not blocks:
        return []

    chunks: list[TextChunk] = []
    cur_parts: list[str] = []
    cur_section: str | None = None
    cur_tokens = 0
    ordinal = 0

    def flush() -> None:
        nonlocal cur_parts, cur_tokens, ordinal
        if not cur_parts:
            return
        body = "\n\n".join(cur_parts).strip()
        if body:
            chunks.append(TextChunk(text=body, section=cur_section, ordinal=ordinal))
            ordinal += 1

    for block, section in blocks:
        block_tokens = estimate_tokens(block)

        # A single block bigger than the budget: hard-split it by words.
        if block_tokens > chunk_tokens:
            flush()
            cur_parts, cur_tokens = [], 0
            words = block.split()
            step = max(1, int(chunk_tokens * 0.75))
            overlap_words = max(0, int(overlap_tokens * 0.75))
            i = 0
            while i < len(words):
                piece = " ".join(words[i : i + step])
                chunks.append(
                    TextChunk(text=piece, section=section, ordinal=ordinal)
                )
                ordinal += 1
                i += max(1, step - overlap_words)
            cur_section = section
            continue

        if cur_tokens + block_tokens > chunk_tokens and cur_parts:
            flush()
            tail = _overlap_tail("\n\n".join(cur_parts), overlap_tokens)
            cur_parts = [tail] if tail else []
            cur_tokens = estimate_tokens(tail) if tail else 0

        cur_parts.append(block)
        cur_tokens += block_tokens
        cur_section = section

    flush()
    return chunks
