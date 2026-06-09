# Internal Documentation RAG

Grounded, cited answers over internal company documentation, behind Google
Workspace SSO. Documents in S3 (PDF / DOCX / Markdown / HTML / TXT) are chunked,
embedded, and indexed in Postgres (pgvector); queries run hybrid retrieval
(dense + lexical) with reranking, then a Claude model — chosen by a cost-aware
routing layer — synthesizes an answer with inline citations.

> **Build status:** Phase 1 (scaffold + local ingestion), the Phase 2 query
> **engine** (hybrid retrieval → rerank → cost-routed Claude generation + eval
> harness), the Phase 2b **HTTP API** (FastAPI `/query` SSE, `/feedback`,
> `/health`), the Phase 3a **web UI** (Next.js + Tailwind + a polished adaptive
> light/dark chat that streams cited answers), and the Phase 3b **Google
> Workspace SSO gate** (OIDC login in Next.js; the backend independently verifies
> the Google ID token on every call) are implemented and tested. Still to come:
> IaC/deploy (Phase 4).

## Architecture (target)

```
              Google SSO (OIDC, hd-gated)
                        │
   Next.js UI ──────────┼─────────► FastAPI backend ──► hybrid retrieval ──► rerank ──► Claude (routed)
   (stream + citations)               /query (SSE)        (pgvector +              Haiku/Sonnet/Opus
                                      /ingest /feedback     tsvector, RRF)
                                      /health
                        ▲
   S3 docs ─► SQS ─► ingest worker ─► loaders → clean → chunk → embed (Voyage) → upsert (pgvector)
   (ObjectCreated/Removed)            (idempotent: doc + chunk content hashes)
```

Every external boundary (embeddings, rerank, LLM, vector DB) is swappable behind
a Protocol in `backend/app/core/interfaces.py`; pgvector can be replaced by a
managed vector DB without touching retrieval or generation.

## Requirements

- Python 3.12
- Docker (for local Postgres + pgvector) — Phase 1 ingestion against a real DB
- A `VOYAGE_API_KEY` (embeddings/rerank) and `ANTHROPIC_API_KEY` (generation).
  These incur cost; nothing calls them until you run ingestion/queries.

## Setup

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1     Unix: source .venv/bin/activate
pip install -e ".[dev,openai]"
cp .env.example .env        # fill in keys; never commit .env
```

> **Windows note:** if `pip install -e .` fails with `WinError 32` on
> `*.egg-info` (a real-time antivirus scanner locking the in-tree build file),
> either add a Defender exclusion for the project folder, or install the
> dependencies directly and run via `PYTHONPATH` — tests and module entrypoints
> work without packaging because the import roots are configured:
> `set PYTHONPATH=backend;.` (PowerShell: `$env:PYTHONPATH="backend;."`).

## Configuration

All knobs live in `backend/app/config.py` and are documented in `.env.example`:
DB URL, document source (local folder vs S3), embedding/rerank provider,
chunking, retrieval top-k's, the model-routing thresholds, and the Google SSO
hosted-domain gate. No secrets are hardcoded; in AWS these come from Secrets
Manager.

## Run locally (Phase 1)

```bash
make db-up                          # start Postgres + pgvector
make migrate                        # apply schema (idempotent)
make ingest SOURCE=./sample_docs    # backfill the index
make ingest SOURCE=./sample_docs    # re-run: everything reports "skipped"
make test                           # unit tests
make lint                           # ruff
```

The ingest run prints a JSON summary: `docs_seen / changed / skipped /
chunks_upserted / chunks_deleted / docs_deleted / failures`. Re-indexing is
idempotent (doc- and chunk-level content hashes) and prunes deleted documents.

### Verify idempotency & deletion without a DB

`python scripts/smoke_phase1.py` imports every module and runs the loaders +
chunker over `sample_docs/` (no DB or API key needed). The idempotency and
deletion-detection logic is covered by `ingestion/tests/test_indexer.py` using
in-memory fakes.

## Run the API (Phase 2b)

The engine is exposed over HTTP by a FastAPI app (`app.main:app`). It needs a
populated DB (`make ingest`) plus `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY`.

```bash
make db-up && make migrate && make ingest          # data
uvicorn app.main:app --reload                      # serve on :8000
# or the full containerized stack (builds backend/Dockerfile):
docker compose --profile full up
```

Endpoints:
- `POST /query` — body `{"query": "...", "history": [...]}`; streams **Server-Sent
  Events**, one per answer event: `meta` (routing decision) → `token`… → `citations`
  → `done`. Try it: `make query Q="How much can I expense for meals?"`.
- `POST /feedback` — `{"query","answer","rating": 1|-1, "comment?", "chunk_ids?"}` →
  `{"id": N}`; persists to the `feedback` table.
- `GET /health` — `200 {"status":"ok"}` when the DB is reachable, else `503`.

By default the API is **open** (`AUTH_ENABLED=false`) — bind to localhost. Set
`AUTH_ENABLED=true` to require a verified Google ID token; see **Auth** below.

## Web UI (Phase 3a)

A polished Next.js 16 + Tailwind v4 chat UI lives in `frontend/`. It streams the
answer token-by-token with inline `[n]` citations, a Sources panel, a routed-model
badge, thumbs up/down feedback, and an **adaptive light/dark theme** (system-aware,
toggle, persisted). The browser talks only to Next.js, which proxies to the
FastAPI backend (so there's no CORS and it's the seam for Phase 3b auth).

```bash
# 1) Backend running (see "Run the API" above), then:
make frontend-install            # cd frontend && npm install
cp frontend/.env.local.example frontend/.env.local   # BACKEND_URL=http://localhost:8000
make frontend                    # cd frontend && npm run dev  → http://localhost:3000
```

Frontend checks: `cd frontend && npm run typecheck && npm test && npm run build`.
With auth disabled (the default) it runs open, exactly like before; flip it on per
the **Auth** section below.

## Auth (Phase 3b) — Google Workspace SSO

The browser only ever talks to Next.js, which acts as the confidential OAuth
client (BFF): it runs the Google **authorization-code + PKCE** flow, stores an
encrypted session cookie, and forwards the user's **Google ID token** to the
backend as `Authorization: Bearer …` (refreshing it transparently when it
nears expiry). The FastAPI backend verifies that token **independently** on every
`/query` and `/feedback` with `google-auth` — signature, audience (the OAuth
client id), and the Workspace `hd` (hosted-domain) claim — so the backend is
secured on its own, not merely trusting the proxy. Login is hand-rolled with
`jose` (no Auth.js); the gate lives in `frontend/proxy.ts`.

**It's off by default.** With `AUTH_ENABLED` unset/false on both sides, the app
behaves exactly like Phase 3a (no sign-in wall, callers are `anonymous@local`) —
so local dev, tests, and CI need no Google credentials. Turn it on for
staging/prod.

To enable it locally you need a one-time Google OAuth client:

1. In [Google Cloud Console](https://console.cloud.google.com/) → **APIs &
   Services → Credentials**, create an **OAuth client ID** of type **Web
   application**.
2. Add the **Authorized redirect URI**: `http://localhost:3000/api/auth/callback`
   (in prod, `${APP_URL}/api/auth/callback`). Scopes used: `openid email profile`.
3. Copy the client id + secret into `frontend/.env.local` and set
   `AUTH_ENABLED=true`, `GOOGLE_HOSTED_DOMAIN=yourcompany.com`,
   `APP_URL=http://localhost:3000`, and an `AUTH_SECRET` (`openssl rand -base64 32`).
4. On the backend set `AUTH_ENABLED=true`, `GOOGLE_OAUTH_CLIENT_ID=<same id>`, and
   `GOOGLE_HOSTED_DOMAIN=yourcompany.com` (see `.env.example`).

Then visiting `/` redirects to `/sign-in`; after Google consent you land on the
chat with a user menu, questions carry your verified identity, accounts outside
the hosted domain are rejected, and "Sign out" clears the session.

## Query engine & evaluation (Phase 2)

The query path is implemented as importable, unit-tested modules (no HTTP yet — the
FastAPI layer is Phase 2b). A query is embedded, searched both ways (dense HNSW +
lexical tsvector), fused with Reciprocal Rank Fusion, reranked, then a cost-aware
router picks a Claude model (Haiku/Sonnet/Opus) that streams a grounded answer with
inline `[n]` citations. If the best reranked chunk falls below `MIN_RERANK_SCORE`,
the engine returns "I don't know" **without** calling Claude. Everything wires up in
`backend/app/deps.py` (`answer_service()`), the seam the future API imports.

```bash
make test                       # all engine unit tests — no DB, no API keys (fakes)
make eval                       # retrieval metrics + LLM-judge groundedness (needs DB + keys)
python -m eval.run_eval --no-judge   # retrieval metrics only — deterministic, no API cost
```

`eval/cases.yaml` holds the question → `expected_doc_ids` cases over `sample_docs/`.
**To add a case**, append an entry (`question:` + `expected_doc_ids:` list of the
doc_ids that should ground a correct answer). `run_eval` reports per-case
hit-rate@k, MRR, recall@k, and (unless `--no-judge`) a groundedness score; the
aggregate row is the mean across cases.

## Layout

| Path | What |
|------|------|
| `backend/app/core/` | Shared contract: DTOs + swappable Protocols |
| `backend/app/embeddings/`, `rerank/`, `vectorstore/`, `llm/` | Provider impls |
| `backend/app/retrieval/`, `generation/`, `deps.py` | Hybrid retrieval, answer orchestration + routing, wiring |
| `backend/app/api/`, `main.py`, `feedback.py` | FastAPI routes (`/query` SSE, `/feedback`, `/health`) + app |
| `backend/app/db/` | pgvector pool + SQL migrations |
| `ingestion/pipeline/` | Loaders, chunking, hashing, sources, indexer, CLI, SQS worker |
| `eval/` | Evaluation harness (Phase 2) |
| `frontend/` | Next.js + Tailwind chat UI — streaming, citations, adaptive theme (Phase 3a) |
| `infra/terraform/` | AWS IaC (Phase 4) |

## Cost (will be finalized with the deploy)

Claude generation dominates; the routing layer is the primary lever — easy,
high-confidence queries go to Haiku ($1/$5 per 1M), typical to Sonnet
($3/$15), and only low-confidence/long-context/complex queries to Opus
($5/$25). Prompt-caching the system + retrieved-context prefix further cuts
repeated-context cost. Voyage embeddings/rerank are cheap; RDS + App Runner are
low-tens of dollars/month at modest traffic.
