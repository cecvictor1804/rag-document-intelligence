"""CI gate: the financial eval (ground-truth figures + reconciliation +
faithfulness over the sample filing) must pass. Offline — no DB, no keys."""

from __future__ import annotations

from eval.financial.run import run_eval


async def test_financial_eval_passes():
    assert await run_eval() == 0
