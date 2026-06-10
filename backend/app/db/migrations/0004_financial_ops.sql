-- Phase 5c/5d: fiscal calendars, FX rates, and the extraction review queue.

-- Entity fiscal calendars: the month the fiscal year ends (12 = calendar).
-- Drives fiscal period labeling for offset-FYE companies (e.g. Apple = 9).
ALTER TABLE entities
    ADD COLUMN IF NOT EXISTS fiscal_year_end_month SMALLINT NOT NULL DEFAULT 12;

-- FX reference rates (ECB daily reference; EUR-based rows, cross rates derived).
CREATE TABLE IF NOT EXISTS fx_rates (
    rate_date      DATE NOT NULL,
    base_currency  TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    rate           NUMERIC NOT NULL,
    PRIMARY KEY (rate_date, base_currency, quote_currency)
);

-- Human-in-the-loop review queue: reconciliation violations recorded at
-- ingest, surfaced via GET /review until resolved.
CREATE TABLE IF NOT EXISTS reconciliation_issues (
    id          BIGSERIAL PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES financial_documents(doc_id) ON DELETE CASCADE,
    check_name  TEXT NOT NULL,
    detail      TEXT NOT NULL,
    expected    NUMERIC,
    actual      NUMERIC,
    resolved    BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (doc_id, check_name, detail)
);
