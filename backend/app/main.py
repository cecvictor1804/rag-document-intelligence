"""FastAPI application entrypoint.

    uvicorn app.main:app --host 0.0.0.0 --port 8000

Thin HTTP shell over the Phase 2 engine: routes call the services assembled in
`app.deps`. Auth (Google SSO) is added in Phase 3 — `/query` is open for now.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.db.pool import close_pool
from app.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(get_settings().log_level)
    yield
    await close_pool()


app = FastAPI(title="Internal Documentation RAG", lifespan=lifespan)
app.include_router(router)
