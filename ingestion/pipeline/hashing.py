"""Content hashing for idempotent re-indexing.

A document's hash drives the skip-unchanged fast path; a chunk's hash is the
upsert key, so only chunks whose text actually changed get re-embedded.
"""

from __future__ import annotations

import hashlib


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
