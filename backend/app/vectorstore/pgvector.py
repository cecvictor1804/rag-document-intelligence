"""pgvector-backed VectorStore: hybrid retrieval + idempotent writes.

Dense search uses the HNSW cosine index; lexical search uses the generated
tsvector with `ts_rank_cd`. Writes are keyed on (doc_id, content_hash) so
re-indexing only inserts genuinely-new chunks, and `delete_missing` /
`delete_documents` prune stale or removed content.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.core.models import Chunk, DocRef, RetrievedChunk
from app.db.pool import get_pool

# Columns selected when reconstructing a Chunk from a row.
_CHUNK_COLS = (
    "chunk_id, doc_id, content_hash, ordinal, section, text, title, "
    "source_url, last_modified, acl"
)


def _row_to_retrieved(row: tuple, score: float, source: str) -> RetrievedChunk:
    (
        chunk_id,
        doc_id,
        content_hash,
        ordinal,
        section,
        text,
        title,
        source_url,
        last_modified,
        acl,
    ) = row
    chunk = Chunk(
        doc_id=doc_id,
        content_hash=content_hash,
        ordinal=ordinal,
        text=text,
        title=title,
        section=section,
        source_url=source_url,
        last_modified=last_modified,
        acl=list(acl or []),
        chunk_id=chunk_id,
    )
    return RetrievedChunk(chunk=chunk, score=score, source=source)


def _acl_clause(acl_filter: Sequence[str] | None, params: list) -> str:
    """Append an ACL predicate when filtering is enabled; no-op in flat mode."""
    if not acl_filter:
        return ""
    params.append(list(acl_filter))
    # Visible if the chunk is world-readable (empty acl) or shares a group.
    return " AND (acl = '{}' OR acl && %s)"


class PgVectorStore:
    # ── Writes ───────────────────────────────────────────────────────────
    async def upsert_document(
        self, ref: DocRef, title: str, content_hash: str, acl: Sequence[str]
    ) -> None:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO documents
                    (doc_id, title, source_url, content_hash,
                     last_modified, filetype, acl, indexed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (doc_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    source_url = EXCLUDED.source_url,
                    content_hash = EXCLUDED.content_hash,
                    last_modified = EXCLUDED.last_modified,
                    filetype = EXCLUDED.filetype,
                    acl = EXCLUDED.acl,
                    indexed_at = now()
                """,
                (
                    ref.doc_id,
                    title,
                    ref.source_url,
                    content_hash,
                    ref.last_modified,
                    ref.filetype,
                    list(acl),
                ),
            )

    async def get_document_hash(self, doc_id: str) -> str | None:
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT content_hash FROM documents WHERE doc_id = %s", (doc_id,)
            )
            row = await cur.fetchone()
            return row[0] if row else None

    async def list_document_ids(self) -> set[str]:
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute("SELECT doc_id FROM documents")
            return {r[0] for r in await cur.fetchall()}

    async def upsert_chunks(self, chunks: Sequence[Chunk]) -> int:
        if not chunks:
            return 0
        pool = await get_pool()
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                for c in chunks:
                    await cur.execute(
                        """
                        INSERT INTO chunks
                            (doc_id, content_hash, ordinal, section, text, embedding,
                             acl, last_modified, source_url, title)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (doc_id, content_hash) DO UPDATE SET
                            ordinal = EXCLUDED.ordinal,
                            section = EXCLUDED.section,
                            acl = EXCLUDED.acl,
                            last_modified = EXCLUDED.last_modified,
                            source_url = EXCLUDED.source_url,
                            title = EXCLUDED.title
                        """,
                        (
                            c.doc_id,
                            c.content_hash,
                            c.ordinal,
                            c.section,
                            c.text,
                            c.embedding,
                            list(c.acl),
                            c.last_modified,
                            c.source_url,
                            c.title,
                        ),
                    )
        return len(chunks)

    async def delete_missing(
        self, doc_id: str, keep_chunk_hashes: Sequence[str]
    ) -> int:
        pool = await get_pool()
        async with pool.connection() as conn:
            if keep_chunk_hashes:
                cur = await conn.execute(
                    "DELETE FROM chunks WHERE doc_id = %s "
                    "AND content_hash <> ALL(%s)",
                    (doc_id, list(keep_chunk_hashes)),
                )
            else:
                cur = await conn.execute(
                    "DELETE FROM chunks WHERE doc_id = %s", (doc_id,)
                )
            return cur.rowcount

    async def delete_documents(self, doc_ids: Sequence[str]) -> int:
        if not doc_ids:
            return 0
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM documents WHERE doc_id = ANY(%s)", (list(doc_ids),)
            )
            return cur.rowcount

    # ── Reads ────────────────────────────────────────────────────────────
    async def dense_search(
        self,
        embedding: Sequence[float],
        top_k: int,
        acl_filter: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        vec = list(embedding)
        # Param order matches the %s order in the SQL below:
        #   SELECT ... <=> vec  |  WHERE acl-clause  |  ORDER BY ... <=> vec  |  LIMIT
        params: list = [vec]
        where = ""
        acl_params: list = []
        acl = _acl_clause(acl_filter, acl_params)
        if acl:
            where = "WHERE TRUE" + acl
            params.extend(acl_params)
        params.extend([vec, top_k])
        sql = (
            f"SELECT {_CHUNK_COLS}, 1 - (embedding <=> %s) AS score "
            f"FROM chunks {where} "
            f"ORDER BY embedding <=> %s LIMIT %s"
        )
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
        return [
            _row_to_retrieved(row[:-1], float(row[-1]), "dense") for row in rows
        ]

    async def lexical_search(
        self,
        query: str,
        top_k: int,
        acl_filter: Sequence[str] | None = None,
    ) -> list[RetrievedChunk]:
        params: list = [query, query]
        acl = _acl_clause(acl_filter, params)
        params.append(top_k)
        sql = (
            f"SELECT {_CHUNK_COLS}, "
            f"ts_rank_cd(tsv, plainto_tsquery('english', %s)) AS score "
            f"FROM chunks "
            f"WHERE tsv @@ plainto_tsquery('english', %s){acl} "
            f"ORDER BY score DESC LIMIT %s"
        )
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(sql, params)
            rows = await cur.fetchall()
        return [
            _row_to_retrieved(row[:-1], float(row[-1]), "lexical") for row in rows
        ]
