from __future__ import annotations

from ingestion.pipeline.hashing import sha256_text


def test_hash_is_stable_and_sensitive():
    assert sha256_text("hello") == sha256_text("hello")
    assert sha256_text("hello") != sha256_text("hello ")
    assert len(sha256_text("x")) == 64
