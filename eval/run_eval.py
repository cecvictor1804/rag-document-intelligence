"""Run the evaluation harness.

    python -m eval.run_eval              # retrieval metrics + groundedness judge
    python -m eval.run_eval --no-judge   # retrieval metrics only (no API/judge cost)
    python -m eval.run_eval --k 8

Needs a populated DB (`make ingest`) and VOYAGE_API_KEY; the judge also needs
ANTHROPIC_API_KEY. Prints a per-case table and aggregate means.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from app import deps
from app.core.models import AnswerEventType, Citation
from app.db.pool import close_pool

from eval.metrics import groundedness_judge, hit_rate_at_k, mrr, recall_at_k

CASES_PATH = Path(__file__).parent / "cases.yaml"


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


async def _run_case(case: dict, k: int, judge: bool) -> dict:
    settings = deps.settings()
    expected = case["expected_doc_ids"]
    question = case["question"]

    reranked = await deps.retrieval_service().retrieve(question)
    retrieved_ids = [r.chunk.doc_id for r in reranked]

    answer_parts: list[str] = []
    citations: list[Citation] = []
    model: str | None = None
    async for ev in deps.answer_service().answer(question):
        if ev.type == AnswerEventType.TOKEN:
            answer_parts.append(ev.data)
        elif ev.type == AnswerEventType.CITATIONS:
            citations = ev.data
        elif ev.type == AnswerEventType.META:
            model = ev.data.get("model")
    answer = "".join(answer_parts)

    row = {
        "question": question,
        "model": model,
        "hit": hit_rate_at_k(retrieved_ids, expected, k),
        "mrr": mrr(retrieved_ids, expected),
        "recall": recall_at_k(retrieved_ids, expected, k),
        "grounded": None,
    }
    if judge:
        verdict = await groundedness_judge(question, answer, citations, settings)
        row["grounded"] = float(verdict.get("score", 0.0))
    return row


async def main() -> None:
    parser = argparse.ArgumentParser(description="RAG evaluation harness")
    parser.add_argument("--k", type=int, default=None, help="top-k for retrieval metrics")
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM groundedness judge")
    args = parser.parse_args()

    k = args.k or deps.settings().rerank_top_k
    cases = yaml.safe_load(CASES_PATH.read_text(encoding="utf-8"))

    try:
        rows = [await _run_case(c, k, judge=not args.no_judge) for c in cases]
    finally:
        await close_pool()

    print(f"\n{'question':<48} {'model':<18} {'hit':>5} {'mrr':>5} {'rec':>5} {'grnd':>5}")
    print("-" * 90)
    for r in rows:
        grnd = f"{r['grounded']:.2f}" if r["grounded"] is not None else "  - "
        print(
            f"{r['question'][:47]:<48} {str(r['model'])[:17]:<18} "
            f"{r['hit']:>5.2f} {r['mrr']:>5.2f} {r['recall']:>5.2f} {grnd:>5}"
        )
    print("-" * 90)
    grounded_scores = [r["grounded"] for r in rows if r["grounded"] is not None]
    print(
        f"{'AGGREGATE (mean)':<48} {'':<18} "
        f"{_mean([r['hit'] for r in rows]):>5.2f} "
        f"{_mean([r['mrr'] for r in rows]):>5.2f} "
        f"{_mean([r['recall'] for r in rows]):>5.2f} "
        f"{(_mean(grounded_scores) if grounded_scores else 0.0):>5.2f}"
    )
    print(f"\n{len(rows)} cases, k={k}, judge={'off' if args.no_judge else 'on'}")


if __name__ == "__main__":
    asyncio.run(main())
