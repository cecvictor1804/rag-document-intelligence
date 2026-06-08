"""Chunking: sizing, overlap, sectioning, and large-block hard-split."""

from __future__ import annotations

from ingestion.pipeline.chunk import chunk_text, estimate_tokens


def test_short_doc_single_chunk_with_section():
    text = "# Passwords\n\nReset links expire after 30 minutes."
    chunks = chunk_text(text, chunk_tokens=600, overlap_tokens=90)
    assert len(chunks) == 1
    assert chunks[0].section == "Passwords"
    assert "30 minutes" in chunks[0].text


def test_multiple_chunks_and_ordinals_are_sequential():
    # Build text that exceeds one chunk.
    paragraphs = [f"Paragraph number {i} with some filler content." * 5 for i in range(40)]
    text = "\n\n".join(paragraphs)
    chunks = chunk_text(text, chunk_tokens=200, overlap_tokens=30)
    assert len(chunks) > 1
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    # No chunk wildly exceeds the budget (allow overlap headroom).
    assert all(estimate_tokens(c.text) <= 200 * 2 for c in chunks)


def test_overlap_carries_context_between_chunks():
    a = "Alpha " * 200
    b = "Bravo " * 200
    text = a.strip() + "\n\n" + b.strip()
    chunks = chunk_text(text, chunk_tokens=150, overlap_tokens=40)
    assert len(chunks) >= 2
    # The second chunk should begin with overlap from the first.
    assert "Alpha" in chunks[1].text


def test_oversized_single_block_is_hard_split():
    huge = "word " * 5000  # one paragraph far bigger than the budget
    chunks = chunk_text(huge, chunk_tokens=300, overlap_tokens=45)
    assert len(chunks) > 1
