"""Cost-aware router: model + effort across confidence and context-length bands."""

from __future__ import annotations

from app.llm.router import route
from fakes import make_chunk, rr, settings


def test_high_confidence_routes_to_cheap():
    ctx = [rr(make_chunk(text="short"), score=0.8)]
    d = route("q", ctx, settings())
    assert d.model == "claude-haiku-4-5"
    assert d.effort == "low"


def test_low_confidence_routes_to_strong():
    ctx = [rr(make_chunk(text="short"), score=0.2)]
    d = route("q", ctx, settings())
    assert d.model == "claude-opus-4-8"
    assert d.effort == "high"


def test_typical_confidence_routes_to_mid():
    ctx = [rr(make_chunk(text="short"), score=0.55)]
    d = route("q", ctx, settings())
    assert d.model == "claude-sonnet-4-6"
    assert d.effort == "medium"  # router_default_effort


def test_long_context_routes_to_strong_even_when_confident():
    # ~150k+ tokens of context (≈4 chars/token) wins over a high score.
    big = make_chunk(text="x" * 620_000)
    d = route("q", [rr(big, score=0.9)], settings())
    assert d.model == "claude-opus-4-8"
    assert d.effort == "high"
    assert "long context" in d.reason


def test_router_disabled_uses_mid():
    ctx = [rr(make_chunk(text="short"), score=0.2)]
    d = route("q", ctx, settings(router_enabled=False))
    assert d.model == "claude-sonnet-4-6"
    assert d.reason == "router disabled"


def test_empty_context_is_low_confidence():
    d = route("q", [], settings())
    assert d.model == "claude-opus-4-8"
