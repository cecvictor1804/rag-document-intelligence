"""Citation extraction and context rendering (pure, no API)."""

from __future__ import annotations

from app.llm.client import build_context_block, extract_citations
from fakes import make_chunk, rr

CTX = [
    rr(make_chunk(doc_id="a.txt", title="Expenses", section="Meals", text="Meal cap is $75/day.")),
    rr(make_chunk(doc_id="b.txt", title="VPN", text="Sign in with SSO.")),
]


def test_extracts_used_markers_dedups_and_bounds():
    answer = "Meals are capped [1]. Also see [1]. Bogus [5]."
    cites = extract_citations(answer, CTX)
    assert [c.n for c in cites] == [1]  # [1] deduped, [5] out of range dropped
    assert cites[0].doc_id == "a.txt"
    assert cites[0].section == "Meals"
    assert cites[0].snippet.startswith("Meal cap")


def test_multiple_markers_in_first_use_order():
    cites = extract_citations("First [2] then [1].", CTX)
    assert [c.n for c in cites] == [2, 1]


def test_no_markers_returns_empty():
    assert extract_citations("I don't know.", CTX) == []


def test_context_block_is_numbered_and_attributed():
    block = build_context_block(CTX)
    assert "[1] Expenses — Meals" in block
    assert "[2] VPN" in block
    assert "Meal cap is $75/day." in block
