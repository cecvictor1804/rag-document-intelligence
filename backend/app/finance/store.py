"""Postgres implementation of the MetricStore Protocol.

Writes facts with their full provenance; reads go through the
`authoritative_facts` view, which resolves conflicts/restatements by authority
rank then filing recency (see migration 0003_financial.sql).
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from app.core.finance import (
    Basis,
    CellRef,
    FinancialDocMeta,
    FinancialFact,
    FiscalPeriod,
    SourceAuthority,
    StatementType,
)
from app.db.pool import get_pool

_FACT_COLUMNS = (
    "fact_id, entity_id, doc_id, statement, line_item, line_item_as_reported, "
    "segment, basis, fiscal_year, fiscal_quarter, period_end, value, "
    "value_as_reported, scale, currency, unit, authority, page, table_index, "
    "row_idx, col_idx"
)


def _row_to_fact(row: tuple[Any, ...]) -> FinancialFact:
    (fact_id, entity_id, doc_id, statement, line_item, as_reported, segment,
     basis, fy, fq, period_end, value, value_as_reported, scale, currency,
     unit, authority, page, table_index, row_idx, col_idx) = row
    cell = (
        CellRef(table_index=table_index, row=row_idx, col=col_idx, page=page)
        if table_index is not None and row_idx is not None and col_idx is not None
        else None
    )
    return FinancialFact(
        entity_id=entity_id,
        doc_id=doc_id,
        statement=StatementType(statement),
        line_item=line_item,
        line_item_as_reported=as_reported,
        segment=segment,
        basis=Basis(basis),
        period=FiscalPeriod(fiscal_year=fy, quarter=fq, end_date=period_end),
        value=Decimal(value),
        value_as_reported=Decimal(value_as_reported),
        scale=int(scale),
        currency=currency,
        unit=unit,
        authority=SourceAuthority(authority),
        cell=cell,
        fact_id=fact_id,
    )


class PgMetricStore:
    async def upsert_entity(
        self, entity_id: str, name: str, ticker: str | None = None,
        cik: str | None = None,
    ) -> None:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO entities (entity_id, name, ticker, cik)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (entity_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        ticker = COALESCE(EXCLUDED.ticker, entities.ticker),
                        cik = COALESCE(EXCLUDED.cik, entities.cik)
                """,
                (entity_id, name, ticker, cik),
            )

    async def upsert_document(self, meta: FinancialDocMeta) -> None:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO financial_documents
                    (doc_id, entity_id, doc_type, authority, filed_date,
                     amends_doc_id, source_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE
                    SET doc_type = EXCLUDED.doc_type,
                        authority = EXCLUDED.authority,
                        filed_date = EXCLUDED.filed_date,
                        amends_doc_id = EXCLUDED.amends_doc_id,
                        source_url = EXCLUDED.source_url
                """,
                (meta.doc_id, meta.entity_id, meta.doc_type, int(meta.authority),
                 meta.filed_date, meta.amends_doc_id, meta.source_url),
            )

    async def upsert_facts(self, facts: Sequence[FinancialFact]) -> int:
        if not facts:
            return 0
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    """
                    INSERT INTO financial_facts
                        (entity_id, doc_id, statement, line_item,
                         line_item_as_reported, segment, basis, fiscal_year,
                         fiscal_quarter, period_end, value, value_as_reported,
                         scale, currency, unit, authority, page, table_index,
                         row_idx, col_idx)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (doc_id, statement, line_item_as_reported,
                                 segment, basis, fiscal_year, fiscal_quarter)
                    DO UPDATE SET
                        line_item = EXCLUDED.line_item,
                        value = EXCLUDED.value,
                        value_as_reported = EXCLUDED.value_as_reported,
                        scale = EXCLUDED.scale,
                        currency = EXCLUDED.currency,
                        unit = EXCLUDED.unit,
                        authority = EXCLUDED.authority,
                        page = EXCLUDED.page,
                        table_index = EXCLUDED.table_index,
                        row_idx = EXCLUDED.row_idx,
                        col_idx = EXCLUDED.col_idx
                    """,
                    [
                        (
                            f.entity_id, f.doc_id, f.statement.value, f.line_item,
                            f.line_item_as_reported, f.segment, f.basis.value,
                            f.period.fiscal_year, f.period.quarter,
                            f.period.end_date, f.value, f.value_as_reported,
                            f.scale, f.currency, f.unit, int(f.authority),
                            f.cell.page if f.cell else None,
                            f.cell.table_index if f.cell else None,
                            f.cell.row if f.cell else None,
                            f.cell.col if f.cell else None,
                        )
                        for f in facts
                    ],
                )
        return len(facts)

    async def get_fact(
        self,
        entity_id: str,
        line_item: str,
        period: FiscalPeriod,
        basis: Basis = Basis.GAAP,
        segment: str | None = None,
    ) -> FinancialFact | None:
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT {_FACT_COLUMNS} FROM authoritative_facts
                WHERE entity_id = %s AND line_item = %s AND basis = %s
                  AND fiscal_year = %s
                  AND fiscal_quarter IS NOT DISTINCT FROM %s
                  AND segment IS NOT DISTINCT FROM %s
                """,
                (entity_id, line_item, basis.value, period.fiscal_year,
                 period.quarter, segment),
            )
            row = await cur.fetchone()
            return _row_to_fact(row) if row else None

    async def get_series(
        self,
        entity_id: str,
        line_item: str,
        basis: Basis = Basis.GAAP,
        segment: str | None = None,
        limit: int = 12,
    ) -> list[FinancialFact]:
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT {_FACT_COLUMNS} FROM authoritative_facts
                WHERE entity_id = %s AND line_item = %s AND basis = %s
                  AND segment IS NOT DISTINCT FROM %s
                ORDER BY fiscal_year DESC, fiscal_quarter DESC NULLS LAST
                LIMIT %s
                """,
                (entity_id, line_item, basis.value, segment, limit),
            )
            rows = await cur.fetchall()
            return [_row_to_fact(r) for r in rows]
