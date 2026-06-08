-- Indexes for hybrid retrieval and idempotent ingestion.

-- Dense retrieval: HNSW over cosine distance. No training step (unlike IVFFlat),
-- strong recall/latency, and it ages well as the corpus grows.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Lexical retrieval over the generated tsvector.
CREATE INDEX IF NOT EXISTS chunks_tsv_gin
    ON chunks USING gin (tsv);

-- Fast chunk lookup / delete by document.
CREATE INDEX IF NOT EXISTS chunks_doc_id
    ON chunks (doc_id);

-- Dormant in flat-access mode; becomes the ACL filter index when per-document
-- permissions are enabled.
CREATE INDEX IF NOT EXISTS chunks_acl_gin
    ON chunks USING gin (acl);

-- Per-user query history (UI shows recent queries).
CREATE INDEX IF NOT EXISTS query_log_user_time
    ON query_log (user_email, created_at DESC);
