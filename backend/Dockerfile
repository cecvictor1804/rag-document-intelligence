# Backend + ingestion image. Builds in Linux, where the editable/egg-info
# Windows file-lock issue does not occur, so a normal install works.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for lxml / psycopg build wheels are not needed (binary wheels),
# but keep ca-certificates for outbound TLS to embeddings/LLM providers.
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
COPY backend ./backend
COPY ingestion ./ingestion
RUN pip install .

# The API serves on 8000; ingestion runs as `python -m ingestion.pipeline.run`.
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
