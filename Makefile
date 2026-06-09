# Developer entrypoints. On Windows, run the underlying commands directly if
# `make` is unavailable (each target is a one-liner you can copy).

PYTHON ?= python
SOURCE ?= ./sample_docs

.PHONY: install db-up db-down migrate ingest reindex query eval test lint typecheck fmt api frontend-install frontend

install:           ## Install backend + ingestion (editable) with dev extras
	$(PYTHON) -m pip install -e ".[dev,openai]"

db-up:             ## Start local Postgres+pgvector
	docker compose up -d db

db-down:           ## Stop local stack
	docker compose down

migrate:           ## Apply SQL migrations to DATABASE_URL
	$(PYTHON) -m app.db.migrate

ingest:            ## Backfill/re-index a folder: make ingest SOURCE=./sample_docs
	$(PYTHON) -m ingestion.pipeline.run --source "$(SOURCE)"

reindex:           ## Alias for ingest (idempotent)
	$(PYTHON) -m ingestion.pipeline.run --source "$(SOURCE)"

query:             ## Run a one-shot query: make query Q="how do I reset my password?"
	curl -N -s -X POST localhost:8000/query -H 'content-type: application/json' \
		-d '{"query": "$(Q)"}'

api:               ## Run the FastAPI backend on :8000
	$(PYTHON) -m uvicorn app.main:app --reload

frontend-install:  ## Install the Next.js frontend deps
	cd frontend && npm install

frontend:          ## Run the Next.js frontend dev server on :3000
	cd frontend && npm run dev

eval:              ## Run the evaluation harness
	$(PYTHON) -m eval.run_eval

test:              ## Run unit tests
	$(PYTHON) -m pytest -q

lint:              ## Lint with ruff
	$(PYTHON) -m ruff check .

typecheck:         ## Type-check with mypy
	$(PYTHON) -m mypy backend/app ingestion

fmt:               ## Auto-format with ruff
	$(PYTHON) -m ruff check --fix . && $(PYTHON) -m ruff format .
