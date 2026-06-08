"""Timeout + bounded retry wrapper for every external call.

Vendor SDKs (Anthropic, Voyage) already retry 429/5xx with backoff; this adds an
app-level wall-clock timeout and a capped exponential backoff so a flaky
embeddings/rerank/LLM/DB call degrades gracefully instead of hanging a request.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

logger = logging.getLogger("rag.resilience")


class ExternalCallError(RuntimeError):
    """Raised when an external call fails after exhausting retries."""


async def with_retry[T](
    fn: Callable[[], Awaitable[T]],
    *,
    what: str,
    attempts: int = 3,
    timeout_s: float = 30.0,
    base_delay_s: float = 0.5,
    max_delay_s: float = 8.0,
) -> T:
    """Run `fn` with a per-attempt timeout and capped exponential backoff.

    `fn` must be a zero-arg coroutine factory (use a lambda/partial) so each
    attempt re-issues a fresh awaitable.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.wait_for(fn(), timeout=timeout_s)
        except TimeoutError as exc:
            last_exc = exc
            logger.warning("%s timed out (attempt %d/%d)", what, attempt, attempts)
        except Exception as exc:  # noqa: BLE001 — retry transient vendor errors
            last_exc = exc
            logger.warning(
                "%s failed (attempt %d/%d): %s", what, attempt, attempts, exc
            )
        if attempt < attempts:
            delay = min(base_delay_s * (2 ** (attempt - 1)), max_delay_s)
            delay += random.uniform(0, delay * 0.25)  # jitter
            await asyncio.sleep(delay)
    raise ExternalCallError(f"{what} failed after {attempts} attempts") from last_exc
