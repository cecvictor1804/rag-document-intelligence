"""RRF fusion: chunks found by both lists outrank chunks found by one."""

from __future__ import annotations

from app.retrieval.fusion import rrf_fuse
from fakes import make_chunk, rc

A = make_chunk(doc_id="a.txt", content_hash="a")
B = make_chunk(doc_id="b.txt", content_hash="b")
C = make_chunk(doc_id="c.txt", content_hash="c")
D = make_chunk(doc_id="d.txt", content_hash="d")


def test_fuses_and_dedupes():
    dense = [rc(A, source="dense"), rc(B, source="dense"), rc(C, source="dense")]
    lexical = [rc(B, source="lexical"), rc(D, source="lexical")]

    fused = rrf_fuse(dense, lexical, rrf_k=60)
    ids = [f.chunk.doc_id for f in fused]

    # B is rank-1 dense AND rank-0 lexical -> highest fused score, ranked first.
    assert ids[0] == "b.txt"
    # Four distinct chunks, deduped on (doc_id, content_hash).
    assert set(ids) == {"a.txt", "b.txt", "c.txt", "d.txt"}
    # Scores are monotonically non-increasing; everything is marked "fused".
    assert all(f.source == "fused" for f in fused)
    assert [f.score for f in fused] == sorted((f.score for f in fused), reverse=True)


def test_empty_lists():
    assert rrf_fuse([], [], rrf_k=60) == []
