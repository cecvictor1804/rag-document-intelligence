"""Cheap, model-agnostic token estimate.

Mirrors the chunker's ≈4-chars/token heuristic (`ingestion.pipeline.chunk`) so
`app` code (e.g. the model router) can size context without importing the
ingestion package. Good enough for routing/sizing; the providers do the real
tokenization.
"""

from __future__ import annotations

import math


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))
