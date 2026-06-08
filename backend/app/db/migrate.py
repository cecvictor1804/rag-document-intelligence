"""Apply SQL migrations in order. Idempotent: each file uses IF NOT EXISTS, and
applied filenames are recorded in a `schema_migrations` table so re-runs skip
already-applied files.

Run with: `python -m app.db.migrate`
"""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg

from app.config import get_settings
from app.logging import configure_logging

logger = logging.getLogger("rag.migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def apply_migrations() -> None:
    settings = get_settings()
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        logger.warning("no migration files found in %s", MIGRATIONS_DIR)
        return

    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "  filename TEXT PRIMARY KEY,"
            "  applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {
            row[0]
            for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }
        for path in files:
            if path.name in applied:
                logger.info("skip %s (already applied)", path.name)
                continue
            logger.info("applying %s", path.name)
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,)
            )
    logger.info("migrations complete (%d file(s) checked)", len(files))


def main() -> None:
    configure_logging(get_settings().log_level)
    apply_migrations()


if __name__ == "__main__":
    main()
