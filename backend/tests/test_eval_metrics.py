"""Retrieval metric functions (pure, deterministic)."""

from __future__ import annotations

from eval.metrics import hit_rate_at_k, mrr, recall_at_k


def test_hit_rate_at_k():
    assert hit_rate_at_k(["a", "b", "c"], ["c"], k=3) == 1.0
    assert hit_rate_at_k(["a", "b", "c"], ["c"], k=2) == 0.0  # c is at rank 3
    assert hit_rate_at_k(["a", "b"], ["z"], k=2) == 0.0


def test_recall_at_k():
    assert recall_at_k(["a", "b", "c"], ["a", "c"], k=3) == 1.0
    assert recall_at_k(["a", "b", "c"], ["a", "z"], k=3) == 0.5
    assert recall_at_k(["a"], [], k=3) == 0.0


def test_mrr():
    assert mrr(["a", "b", "c"], ["a"]) == 1.0
    assert mrr(["a", "b", "c"], ["b"]) == 0.5
    assert mrr(["a", "b", "c"], ["c"]) == 1.0 / 3
    assert mrr(["a", "b"], ["z"]) == 0.0
