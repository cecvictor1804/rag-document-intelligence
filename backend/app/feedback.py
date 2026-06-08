"""Persist thumbs up/down feedback on answers (the `feedback` table).

Stored for later evaluation. `user_email` is "anonymous" until Phase 3 adds the
Google SSO gate (the column is NOT NULL).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from app.db.pool import get_pool


class Feedback(Protocol):
    async def record(
        self,
        *,
        query: str,
        answer: str | None,
        rating: int,
        comment: str | None,
        chunk_ids: Sequence[int],
        user_email: str = "anonymous",
    ) -> int: ...


class PgFeedback:
    async def record(
        self,
        *,
        query: str,
        answer: str | None,
        rating: int,
        comment: str | None,
        chunk_ids: Sequence[int],
        user_email: str = "anonymous",
    ) -> int:
        pool = await get_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO feedback
                    (query, answer, rating, comment, user_email, chunk_ids)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (query, answer, rating, comment, user_email, list(chunk_ids)),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0  # RETURNING always yields a row
