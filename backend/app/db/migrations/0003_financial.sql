-- Phase 5a: the canonical financial fact store.
-- Money is NUMERIC end to end; every fact carries cell-level provenance and the
-- source-precedence inputs (authority rank + filing date) used to resolve
-- conflicts/restatements in the authoritative_facts view.

-- Tracked companies (the watchlist). entity_id is a stable slug (ticker today).
CREATE TABLE IF NOT EXISTS entities (
    entity_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    ticker      TEXT,
    cik         TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Financial-document metadata. Distinct from the RAG `documents` table: a doc
-- can appear in both (narrative chunks there, extracted facts here).
CREATE TABLE IF NOT EXISTS financial_documents (
    doc_id        TEXT PRIMARY KEY,
    entity_id     TEXT NOT NULL REFERENCES entities(entity_id),
    doc_type      TEXT NOT NULL,                -- 10-K | 10-Q | 10-K/A | press_release | other
    authority     SMALLINT NOT NULL DEFAULT 0,  -- SourceAuthority rank
    filed_date    DATE,
    amends_doc_id TEXT REFERENCES financial_documents(doc_id),
    source_url    TEXT NOT NULL DEFAULT '',
    ingested_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per reported figure. `value` is normalized to base units (dollars,
-- shares); `value_as_reported`/`scale`/`currency` preserve what was printed.
-- `line_item` is the canonical concept (NULL when unmapped); the as-reported
-- label is always kept. (page, table_index, row_idx, col_idx) is the cited cell.
CREATE TABLE IF NOT EXISTS financial_facts (
    fact_id                BIGSERIAL PRIMARY KEY,
    entity_id              TEXT NOT NULL REFERENCES entities(entity_id),
    doc_id                 TEXT NOT NULL REFERENCES financial_documents(doc_id) ON DELETE CASCADE,
    statement              TEXT NOT NULL,            -- income | balance | cash_flow | other
    line_item              TEXT,                     -- canonical (chart of accounts)
    line_item_as_reported  TEXT NOT NULL,
    segment                TEXT,                     -- NULL == consolidated
    basis                  TEXT NOT NULL DEFAULT 'gaap',
    fiscal_year            INT NOT NULL,
    fiscal_quarter         SMALLINT,                 -- NULL == full year
    period_end             DATE,
    value                  NUMERIC NOT NULL,
    value_as_reported      NUMERIC NOT NULL,
    scale                  BIGINT NOT NULL DEFAULT 1,
    currency               TEXT NOT NULL DEFAULT 'USD',
    unit                   TEXT NOT NULL DEFAULT 'currency',
    authority              SMALLINT NOT NULL DEFAULT 0,
    page                   INT,
    table_index            INT,
    row_idx                INT,
    col_idx                INT,
    reconciled             BOOLEAN,                  -- NULL == not checked
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Re-ingesting the same document replaces its facts (NULLS NOT DISTINCT so
    -- consolidated/FY rows collide as intended; requires Postgres 15+).
    UNIQUE NULLS NOT DISTINCT (doc_id, statement, line_item_as_reported, segment,
                               basis, fiscal_year, fiscal_quarter)
);

CREATE INDEX IF NOT EXISTS financial_facts_lookup
    ON financial_facts (entity_id, line_item, basis, fiscal_year, fiscal_quarter);

-- Conflict resolution: for each (entity, concept, segment, basis, period), the
-- winning fact is the one from the highest-authority document, ties broken by
-- filing recency (so the latest restatement supersedes), then by insert order.
-- Alternates remain queryable in financial_facts.
CREATE OR REPLACE VIEW authoritative_facts AS
SELECT DISTINCT ON (
        f.entity_id, f.statement,
        COALESCE(f.line_item, f.line_item_as_reported),
        COALESCE(f.segment, ''), f.basis, f.fiscal_year, COALESCE(f.fiscal_quarter, 0)
    )
    f.*
FROM financial_facts f
JOIN financial_documents d USING (doc_id)
ORDER BY
    f.entity_id, f.statement,
    COALESCE(f.line_item, f.line_item_as_reported),
    COALESCE(f.segment, ''), f.basis, f.fiscal_year, COALESCE(f.fiscal_quarter, 0),
    f.authority DESC, d.filed_date DESC NULLS LAST, f.fact_id DESC;
