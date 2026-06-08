-- Initial schema for the documentation RAG system.
-- pgvector provides the `vector` type used by the chunks table.

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per source document. `content_hash` is the doc-level sha256 used to
-- skip unchanged documents on re-index. `acl` is empty in flat mode; reserved
-- so per-document permissions can be enabled later without a migration.
CREATE TABLE IF NOT EXISTS documents (
    doc_id        TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    last_modified TIMESTAMPTZ,
    filetype      TEXT NOT NULL,
    acl           TEXT[] NOT NULL DEFAULT '{}',
    indexed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per chunk. The (doc_id, content_hash) pair is the upsert key, so only
-- changed chunks are re-embedded. `tsv` is generated so lexical search stays in
-- sync with `text` automatically. `embedding` dimension must match
-- EMBEDDING_DIM (default 1024 for voyage-3).
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      BIGSERIAL PRIMARY KEY,
    doc_id        TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    content_hash  TEXT NOT NULL,
    ordinal       INT NOT NULL,
    section       TEXT,
    text          TEXT NOT NULL,
    embedding     vector(1024) NOT NULL,
    tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
    acl           TEXT[] NOT NULL DEFAULT '{}',
    last_modified TIMESTAMPTZ,
    source_url    TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL DEFAULT '',
    UNIQUE (doc_id, content_hash)
);

-- Thumbs up/down feedback on answers, stored for later evaluation.
CREATE TABLE IF NOT EXISTS feedback (
    id          BIGSERIAL PRIMARY KEY,
    query       TEXT NOT NULL,
    answer      TEXT,
    rating      SMALLINT NOT NULL,           -- +1 / -1
    comment     TEXT,
    user_email  TEXT NOT NULL,
    chunk_ids   BIGINT[] NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Observability: one row per query, including the routing decision so model
-- selection can be evaluated and re-tuned.
CREATE TABLE IF NOT EXISTS query_log (
    id            BIGSERIAL PRIMARY KEY,
    user_email    TEXT NOT NULL,
    query         TEXT NOT NULL,
    model         TEXT,
    route_reason  TEXT,
    top_score     REAL,
    n_results     INT,
    latency_ms    INT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
