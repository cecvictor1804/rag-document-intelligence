"""Financial ingestion: parse → map facts → reconcile → store.

The numeric counterpart of the narrative Indexer. One document flows through
the FinancialParser (tables + text), the fact mapper (normalized facts with
cell provenance), the reconciliation invariants (extraction distrust), and into
the canonical metric store. Reconciliation issues are surfaced in the summary —
a violation means "inspect this document", not "discard it".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.core.finance import FinancialDocMeta, SourceAuthority
from app.core.interfaces import FinancialParser, MetricStore
from app.core.models import DocRef

from ingestion.pipeline.facts import map_document_tables
from ingestion.pipeline.reconcile import reconcile

logger = logging.getLogger("rag.financial")

# Filename/doc-id patterns → (doc_type, authority). Order matters: amendments
# before their base form. (?![a-z0-9]) instead of \b because filenames use
# underscores, which \b treats as word characters.
_DOC_TYPES: tuple[tuple[re.Pattern[str], str, SourceAuthority], ...] = (
    (re.compile(r"10-?k[\s_/-]?a(?![a-z0-9])", re.I), "10-K/A", SourceAuthority.AMENDMENT),
    (re.compile(r"10-?q[\s_/-]?a(?![a-z0-9])", re.I), "10-Q/A", SourceAuthority.AMENDMENT),
    (re.compile(r"10-?k(?![a-z0-9])", re.I), "10-K", SourceAuthority.ANNUAL_FILING),
    (re.compile(r"10-?q(?![a-z0-9])", re.I), "10-Q", SourceAuthority.QUARTERLY_FILING),
    (re.compile(r"8-?k(?![a-z0-9])|press|earnings[\s_-]?release", re.I),
     "press_release", SourceAuthority.PRESS_RELEASE),
)


def infer_doc_type(name: str) -> tuple[str, SourceAuthority]:
    """Document type + precedence rank from a filename/doc id."""
    for pattern, doc_type, authority in _DOC_TYPES:
        if pattern.search(name):
            return doc_type, authority
    return "other", SourceAuthority.OTHER


@dataclass(slots=True)
class FinancialIngestSummary:
    doc_id: str
    doc_type: str
    tables_seen: int = 0
    facts_upserted: int = 0
    facts_mapped_canonical: int = 0
    reconciliation_issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_type": self.doc_type,
            "tables_seen": self.tables_seen,
            "facts_upserted": self.facts_upserted,
            "facts_mapped_canonical": self.facts_mapped_canonical,
            "reconciliation_issues": self.reconciliation_issues,
        }


class FinancialIngestor:
    def __init__(self, parser: FinancialParser, store: MetricStore) -> None:
        self.parser = parser
        self.store = store

    async def ingest(
        self,
        ref: DocRef,
        content: bytes,
        entity_id: str,
        entity_name: str | None = None,
        doc_type: str | None = None,
        filed_date: date | None = None,
    ) -> FinancialIngestSummary:
        inferred_type, authority = infer_doc_type(doc_type or ref.doc_id)
        meta = FinancialDocMeta(
            doc_id=ref.doc_id,
            entity_id=entity_id,
            doc_type=doc_type or inferred_type,
            authority=authority,
            filed_date=filed_date,
            source_url=ref.source_url,
        )

        parsed = await self.parser.parse(ref, content)
        facts = map_document_tables(parsed.tables, meta)
        issues = reconcile(facts)
        for issue in issues:
            logger.warning(
                "reconciliation: %s (expected %s, got %s)",
                issue.detail, issue.expected, issue.actual,
            )

        await self.store.upsert_entity(entity_id, entity_name or entity_id)
        await self.store.upsert_document(meta)
        upserted = await self.store.upsert_facts(facts)

        return FinancialIngestSummary(
            doc_id=ref.doc_id,
            doc_type=meta.doc_type,
            tables_seen=len(parsed.tables),
            facts_upserted=upserted,
            facts_mapped_canonical=sum(1 for f in facts if f.line_item),
            reconciliation_issues=[i.detail for i in issues],
        )
