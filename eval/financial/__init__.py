"""Financial evaluation: ground-truth figures, reconciliation, faithfulness.

Deterministic and offline — no DB, no API keys: the sample filing(s) run
through the real extraction pipeline into an in-memory store, and every case
asserts an exact expected number. Run: `python -m eval.financial`.
"""
