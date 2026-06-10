"""Financial eval runner: extraction + compute accuracy, end to end, offline.

Three layers per run:
1. **Reconciliation** — every ingested document must pass its invariants.
2. **Ground-truth figures** — each case in cases.yaml must resolve to exactly
   the expected value (within optional absolute tolerance).
3. **Faithfulness self-check** — for each case, a narration of the correct
   value must verify, and a corrupted one must be flagged.

Exit code 1 on any failure, so CI can gate on it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from app.core.finance import Basis, FinancialDocMeta, FinancialFact, FiscalPeriod
from app.core.models import DocRef
from app.extraction.html_table import HtmlTableParser
from app.finance.service import MetricService
from app.finance.verify import is_faithful

from ingestion.pipeline.financial import FinancialIngestor

ROOT = Path(__file__).resolve().parents[2]
CASES = Path(__file__).parent / "cases.yaml"


@dataclass
class InMemoryMetricStore:
    """MetricStore over a list — authority precedence, no Postgres."""

    facts: list[FinancialFact] = field(default_factory=list)
    documents: list[FinancialDocMeta] = field(default_factory=list)

    async def upsert_entity(self, entity_id, name, ticker=None, cik=None,
                            fye_month=None):
        pass

    async def upsert_document(self, meta: FinancialDocMeta) -> None:
        self.documents.append(meta)

    async def upsert_facts(self, facts) -> int:
        self.facts.extend(facts)
        return len(facts)

    async def record_issues(self, issues) -> None:
        pass

    async def list_open_issues(self, limit: int = 50):
        return []

    async def upsert_fx_rates(self, rows) -> int:
        return 0

    async def get_fx_rate(self, base, quote, as_of=None):
        return None

    def _match(self, f: FinancialFact, entity_id, line_item, basis, segment) -> bool:
        return (
            f.entity_id == entity_id
            and f.line_item == line_item
            and f.basis is basis
            and f.segment == segment
        )

    async def get_fact(
        self, entity_id, line_item, period: FiscalPeriod,
        basis: Basis = Basis.GAAP, segment=None,
    ) -> FinancialFact | None:
        candidates = [
            f for f in self.facts
            if self._match(f, entity_id, line_item, basis, segment)
            and f.period.fiscal_year == period.fiscal_year
            and f.period.quarter == period.quarter
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda f: f.authority)

    async def get_series(
        self, entity_id, line_item, basis: Basis = Basis.GAAP,
        segment=None, limit: int = 12,
    ) -> list[FinancialFact]:
        matched = [
            f for f in self.facts
            if self._match(f, entity_id, line_item, basis, segment)
        ]
        matched.sort(
            key=lambda f: (f.period.fiscal_year, f.period.quarter or 0),
            reverse=True,
        )
        return matched[:limit]


async def run_eval() -> int:
    spec: dict[str, Any] = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    entity: str = spec["entity"]

    store = InMemoryMetricStore()
    ingestor = FinancialIngestor(HtmlTableParser(), store)
    failures = 0

    # 1. Ingest + reconciliation gate.
    for rel in spec["files"]:
        path = ROOT / rel
        ref = DocRef(doc_id=path.name, source_url=path.as_uri(), filetype="html")
        summary = await ingestor.ingest(
            ref, path.read_bytes(), entity, spec.get("entity_name")
        )
        status = "ok" if not summary.reconciliation_issues else "FAIL"
        if summary.reconciliation_issues:
            failures += 1
        print(
            f"[reconcile] {status:4} {rel}: {summary.facts_upserted} facts, "
            f"{len(summary.reconciliation_issues)} issue(s)"
        )

    # 2 + 3. Ground-truth figures + faithfulness self-check.
    service = MetricService(store)
    for case in spec["cases"]:
        period = FiscalPeriod(
            fiscal_year=case["fiscal_year"], quarter=case.get("fiscal_quarter")
        )
        expected = Decimal(str(case["expected"]))
        tolerance = Decimal(str(case.get("tolerance", "0")))
        label = f"{case['metric']} {period.label}"

        result = await service.resolve(entity, case["metric"], period)
        if result is None:
            failures += 1
            print(f"[figures]   FAIL {label}: no result (facts missing)")
            continue

        if abs(result.value - expected) > tolerance:
            failures += 1
            print(f"[figures]   FAIL {label}: expected {expected}, got {result.value}")
            continue
        print(f"[figures]   ok   {label} = {result.value}")

        suffix = "%" if result.unit == "percent" else ""
        truthful = f"The {case['metric']} for {period.label} was {result.value}{suffix}."
        corrupted = (
            f"The {case['metric']} for {period.label} was "
            f"{(result.value * Decimal('1.17')).quantize(Decimal('0.001'))}{suffix}."
        )
        ok = is_faithful(truthful, [result.value]) and not is_faithful(
            corrupted, [result.value]
        )
        if not ok:
            failures += 1
            print(f"[faithful]  FAIL {label}: verifier did not behave as expected")

    print(f"\n{'PASS' if failures == 0 else 'FAIL'} — {failures} failure(s)")
    return 1 if failures else 0


def main() -> None:
    raise SystemExit(asyncio.run(run_eval()))
