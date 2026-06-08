"""Best-effort observability sink for the `query_log` table.

The answer service calls `record(...)` once per query with the routing decision
and timing. `user_email` is "" until Phase 3 adds auth (the column is NOT NULL).
Failures here must never break answering, so the caller wraps it defensively.
"""

from __future__ import annotations

from typing import Protocol

from app.db.pool import get_pool


class QueryLog(Protocol):
    async def record(
        self,
        *,
        query: str,
        model: str | None,
        route_reason: str | None,
        top_score: float | None,
        n_results: int,
        latency_ms: int,
        user_email: str = "",
    ) -> None: ...


class PgQueryLog:
    async def record(
        self,
        *,
        query: str,
        model: str | None,
        route_reason: str | None,
        top_score: float | None,
        n_results: int,
        latency_ms: int,
        user_email: str = "",
    ) -> None:
        pool = await get_pool()
        async with pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO query_log
                    (user_email, query, model, route_reason,
                     top_score, n_results, latency_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (user_email, query, model, route_reason, top_score, n_results, latency_ms),
            )
