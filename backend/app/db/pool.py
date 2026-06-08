"""Async Postgres connection pool with pgvector registered.

A single module-level pool is created lazily and reused. `register_vector` is
configured per connection so `list[float]` round-trips to the `vector` type.
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from app.config import get_settings

_pool: AsyncConnectionPool | None = None


async def _configure(conn) -> None:  # type: ignore[no-untyped-def]
    # Register the pgvector adapter on each pooled connection.
    from pgvector.psycopg import register_vector_async

    await register_vector_async(conn)


async def get_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=10,
            open=False,
            configure=_configure,
            kwargs={"autocommit": True},
        )
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
