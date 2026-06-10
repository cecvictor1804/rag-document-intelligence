# Financial Document Intelligence

Grounded, cited, and **computed** answers over financial documents — SEC filings
(10-K/10-Q), earnings materials, and internal statements — behind Google Workspace
SSO. Unlike a generic document chatbot, **tables and numbers are first-class**: figures
are extracted into a canonical metric store with **cell-level provenance**, metrics
(YoY growth, margins, ratios) are **computed deterministically** rather than guessed
by an LLM, and every number in an answer cites the exact source cell it came from.

> **Build status (honest).** Built and tested through **Phase 5b**: the platform
> (Phases 1–4: ingestion → hybrid retrieval → cost-routed Claude → FastAPI SSE
> API → Next.js UI → Google SSO → AWS ECS Fargate deploy), the **5a financial
> core** (structured table extraction — built-in HTML parser + AWS Textract
> adapter — canonical metric store with cell-level provenance and restatement
> precedence, deterministic metric computation, citation-faithfulness
> verification, hard advice guardrails, `POST /metrics` + a metrics panel, and
> an offline financial eval), **5b unified querying** (an NL→query planner that
> merges verified figures into chat answers with metric cards + trend charts
> and post-stream number verification, plus the EDGAR watchlist feed), and
> **5c/5d depth & ops** (entity fiscal calendars with EDGAR auto-detect,
> annotated FX conversion from ECB reference rates, ratio trend series,
> GAAP↔non-GAAP counterparts, segment revenue, async multi-page Textract, a
> parallel financial path in the SQS worker, and a human-in-the-loop review
> queue). Remaining ideas live in the [Roadmap](#roadmap).

## Contents

- [Why finance is different](#why-finance-is-different) · [Architecture](#architecture) · [How it works](#how-it-works)
- [Requirements](#requirements) · [Setup](#setup) · [Configuration](#configuration)
- [Running the stack](#running-the-stack) · [API endpoints](#api-endpoints) · [Authentication](#authentication)
- [Evaluation](#evaluation) · [Testing](#testing) · [Deployment](#deployment)
- [Roadmap](#roadmap) · [Project layout](#project-layout) · [Cost](#cost)

## Why finance is different

Plain RAG retrieves and paraphrases text. That fails on financial documents for four
reasons, and the design exists to address each:

- **The numbers live in tables.** A balance sheet flattened to text becomes an
  unaligned word-soup; "what was Q3 revenue" can't be answered reliably from it. We
  extract tables as structured cells, not prose.
- **Answers must be computed, not retrieved.** YoY growth, gross margin, and the
  current ratio are arithmetic over figures — done in **code**, deterministically,
  never freehand by the model.
- **Comparisons span periods and documents.** Trends (QoQ, multi-quarter) require a
  period-aligned model across filings, including restatements.
- **A wrong number is unacceptable.** Every figure is tied to an exact source cell and
  **verified** after generation; unsupported numbers are suppressed. The assistant
  gives factual analysis only — **no buy/sell/hold advice**.

## Architecture

```
          Google Workspace SSO (OIDC, hd-gated)
                        │
  Next.js UI ───────────┼───► FastAPI ──┬─► /query    (narrative, SSE)
  chat + metrics panel  │               ├─► /metrics  (figure + source cell, no LLM)
  with cell provenance  │               └─► /feedback · /health
                        ▼
  ┌─ narrative substrate ───────────────────┐   ┌─ numeric substrate ────────────────────────┐
  │ loaders → chunk → embed (Voyage) →       │   │ parser (HTML built-in | Textract for PDFs) │
  │ pgvector; hybrid retrieval → rerank →    │   │ → fact mapper (units/scale/currency norm,  │
  │ cost-routed Claude with [n] citations    │   │   canonical + as-reported line items,      │
  └──────────────────────────────────────────┘   │   fiscal periods, GAAP/non-GAAP, segment,  │
                                                  │   cell provenance) → reconciliation        │
  documents ─► ingest CLI/worker ─► both          │ → canonical metric store (restatement      │
  S3 upload · manual files ·                      │   lineage, source precedence)              │
  EDGAR watchlist feed (make edgar-sync)          │ → deterministic compute (ratios/growth)    │
                                                  │ → cite-cell + verify → advice guardrails   │
                                                  └────────────────────────────────────────────┘
  chat question ─► NL→query planner (cheap Claude call) ─► verified figures merged into the
  streamed answer (metric cards + trend charts); every number checked post-stream
```

Every external boundary (embeddings, rerank, LLM, vector DB, and the **financial
parser**) is swappable behind a Protocol in `backend/app/core/interfaces.py` — the
extraction vendor, like the vector DB, can be replaced without touching the rest
of the system (`FINANCIAL_PARSER=html|textract`).

## How it works

**Ingestion — narrative (built).** Loaders read each document
(PDF/DOCX/Markdown/HTML/TXT), clean and chunk it, embed the chunks with Voyage, and
upsert them into pgvector. The run is **idempotent** — doc- and chunk-level content
hashes mean re-indexing only touches what changed and prunes deleted documents. The
CLI prints a JSON summary: `docs_seen / changed / skipped / chunks_upserted /
chunks_deleted / docs_deleted / failures`.

**Ingestion — numeric (built).** A financial parser turns tables into structured
cells — the built-in HTML parser for native-HTML filings (what EDGAR 10-K/10-Qs
are), or **AWS Textract** for PDFs/scans (chosen because the deploy is already
AWS: documents stay in-account, IAM instead of vendor API keys; multi-page
documents use the async S3-based analysis with a page-count cost flag). A
**fact mapper** normalizes scale/currency/units (storing a canonical base value
alongside the as-reported one), maps line items to a canonical chart while
**keeping the company's own label**, resolves the fiscal period **on the
entity's own fiscal calendar** (offset FYEs auto-detected from EDGAR), tags
GAAP vs non-GAAP (adjusted labels pair with their GAAP counterparts), extracts
**segment revenue** from revenue-by-segment tables, and attaches
**page/table/row/col provenance**. **Reconciliation invariants** (Assets = Liabilities + Equity;
Revenue − CoR = Gross profit) flag bad extractions instead of trusting them.
Facts land in the **canonical metric store** with restatement lineage and a
**source-precedence hierarchy** (audited filing > amendment > press release;
latest restatement wins; alternates kept). Ingest with
`make ingest-financial ENTITY=ACME FILES="sample_docs/acme_corp_10q_q3_2024.html"`.

**Query — narrative (built).** A question is embedded and searched both ways (dense
HNSW + lexical tsvector), fused with Reciprocal Rank Fusion, reranked, then a
cost-aware router picks a Claude model (Haiku/Sonnet/Opus) that streams a grounded
answer with inline `[n]` citations. Below `MIN_RERANK_SCORE`, it returns "I don't
know" **without** calling Claude. Wiring lives in `backend/app/deps.py`.

**Query — numeric (built).** `POST /metrics` (and the UI's metrics panel)
resolves a figure or ratio **deterministically — no LLM in the path**: the
compute layer runs the math and returns the exact source facts with their cells.
**Hard advice guardrails** refuse buy/sell/hold questions before retrieval or
generation.

**Query — unified (built, 5b).** In chat, an **NL→query planner** (one cheap
Claude call, restricted to the legal metric vocabulary; any failure degrades to
narrative-only) decides which verified figures the question needs. They're
resolved deterministically, streamed as **metric cards** and **trend charts**,
and appended to the model's input as a "verified figures" block so the narration
uses exact values. After streaming, a **citation-faithfulness check** compares
every number in the answer against the verified figures + numbers present in the
retrieved passages; anything unbacked is flagged in the UI ("n numbers could not
be verified").

**Frontend / auth (built).** The browser talks **only** to Next.js, which proxies to
the FastAPI backend (no CORS) and acts as the OAuth client when auth is on — see
[Authentication](#authentication).

## Requirements

- Python 3.12
- Docker (for local Postgres + pgvector)
- A `VOYAGE_API_KEY` (embeddings/rerank) and `ANTHROPIC_API_KEY` (generation).
  These incur cost; nothing calls them until you run ingestion/queries.
- Node 20+ (only for the web UI).
- AWS credentials only if you set `FINANCIAL_PARSER=textract` (PDF/scan
  extraction; per-page cost). HTML filings need nothing extra.

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
DB URL, document source (local folder vs S3), embedding/rerank provider, chunking,
retrieval top-k's, the model-routing thresholds, the financial parser
(`FINANCIAL_PARSER=html|textract`), and the Google SSO hosted-domain gate. No
secrets are hardcoded; in AWS these come from Secrets Manager.

## Running the stack

### 1. Ingest documents

```bash
make db-up                          # start Postgres + pgvector
make migrate                        # apply schema (idempotent)
make ingest SOURCE=./sample_docs    # narrative index (chunks + embeddings)
# numeric facts: extract a filing into the metric store
make ingest-financial ENTITY=ACME FILES="sample_docs/acme_corp_10q_q3_2024.html"
# or pull real filings from SEC EDGAR (needs EDGAR_USER_AGENT in .env):
make edgar-sync ENTITY=AAPL CIK=320193
```

No DB handy? `python scripts/smoke_phase1.py` imports every module and runs the
loaders + chunker over `sample_docs/` (no DB or API key needed).

### 2. Run the API

The engine is exposed over HTTP by a FastAPI app (`app.main:app`). It needs a
populated DB (step 1) plus `VOYAGE_API_KEY` and `ANTHROPIC_API_KEY`.

```bash
uvicorn app.main:app --reload          # serve on :8000
# or the full containerized stack (builds backend/Dockerfile):
docker compose --profile full up
```

By default the API is **open** (`AUTH_ENABLED=false`) — bind to localhost. Set
`AUTH_ENABLED=true` to require a verified Google ID token; see
[Authentication](#authentication).

### 3. Run the web UI

A polished Next.js 16 + Tailwind v4 chat UI lives in `frontend/`. It streams the
answer token-by-token with inline `[n]` citations, **metric cards and trend
charts** for planner-resolved figures, a Sources panel, a routed-model badge,
thumbs up/down feedback, and an **adaptive light/dark theme**. The **metrics
panel** (chart icon in the header) looks up figures/ratios deterministically —
with optional FX conversion and the non-GAAP counterpart — shows the exact
source cell of every input, and surfaces flagged extractions in its **Data
quality** section.

```bash
# With the API running (step 2):
make frontend-install            # cd frontend && npm install
cp frontend/.env.local.example frontend/.env.local   # BACKEND_URL=http://localhost:8000
make frontend                    # cd frontend && npm run dev  → http://localhost:3000
```

## API endpoints

- `POST /query` — body `{"query": "...", "history": [...]}`; streams **Server-Sent
  Events**, one per answer event: `meta` (routing decision) → `token`… → `citations`
  → `done`. The narrative substrate. Try it: `make query Q="..."`.
- `POST /feedback` — `{"query","answer","rating": 1|-1, "comment?", "chunk_ids?"}` →
  `{"id": N}`; persists to the `feedback` table (attributed to the signed-in user when
  auth is on, else `anonymous@local`).
- `GET /review` — open reconciliation issues (extractions a human should look
  at), newest first.
- `GET /health` — `200 {"status":"ok"}` when the DB is reachable, else `503`.
- `POST /metrics` — `{"entity","metric","fiscal_year","fiscal_quarter?","basis?",
  "segment?","currency?"}` → the value (Decimal-as-string for exactness) plus,
  per input figure, the **exact source cell** (doc, page, table, row, col) and
  the as-reported label/value/scale; optional extras are **annotated, never
  silent**: `converted` (FX value + applied rate + as-of date) and
  `non_gaap_alternative` (the adjusted counterpart, clearly tagged). `metric` is
  a canonical line item (`revenue`), a ratio (`gross_margin`), or a YoY growth
  (`revenue_yoy`). Deterministic — no LLM.

## Authentication

Google Workspace SSO (Phase 3b). It is **off by default**: with `AUTH_ENABLED`
unset/false on both sides the app runs open (no sign-in wall, callers are
`anonymous@local`), so local dev, tests, and CI need no Google credentials.

When on, the Next.js frontend acts as the confidential OAuth client (BFF): it runs
the Google **authorization-code + PKCE** flow, stores an encrypted session cookie,
and forwards the user's **Google ID token** to the backend as `Authorization:
Bearer …` (refreshing it transparently near expiry). The FastAPI backend verifies
that token **independently** on every `/query` and `/feedback` with `google-auth`
— signature, audience (the OAuth client id), and the Workspace `hd` (hosted-domain)
claim — so the backend is secured on its own, not merely trusting the proxy. Login
is hand-rolled with `jose` (no Auth.js); the gate lives in `frontend/proxy.ts`.

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
chat, questions carry your verified identity, accounts outside the hosted domain are
rejected, and "Sign out" clears the session.

## Evaluation

```bash
make eval                            # retrieval metrics + LLM-judge groundedness (needs DB + keys)
python -m eval.run_eval --no-judge   # retrieval metrics only — deterministic, no API cost
```

`eval/cases.yaml` holds question → `expected_doc_ids` cases; `run_eval` reports per-case
hit-rate@k, MRR, recall@k, and (unless `--no-judge`) an LLM-judge groundedness score.

**Numeric eval (built).** Retrieval + judge can't check arithmetic, so the
financial eval adds three deterministic layers — a **ground-truth figure set**
(`eval/financial/cases.yaml`: metric → exact expected value), **reconciliation
invariants**, and a **citation-faithfulness self-check** — run end-to-end through
the real parser/mapper/compute with an in-memory store:

```bash
make eval-financial    # fully offline: no DB, no API keys; CI gate via pytest
```

## Testing

```bash
make test        # backend + ingestion unit tests — no DB, no API keys (fakes)
make lint        # ruff
make typecheck   # mypy
```

Frontend: `cd frontend && npm run typecheck && npm test && npm run build`.

## Deployment

**Whole stack in containers, locally:**

```bash
docker compose --profile full up --build   # db + migrate + backend API + web UI → :3000
```

**AWS (ECS Fargate).** `infra/terraform/` provisions a VPC, RDS Postgres (pgvector),
an S3 docs bucket wired to SQS, ECR, Secrets Manager, and a Fargate cluster running
three services — the **frontend** behind a public ALB, the **backend** reached
privately over ECS Service Connect, and the long-polling **ingest worker** (S3 → SQS →
re-index). One backend image serves the API, the worker, and migrations. See
[infra/terraform/README.md](infra/terraform/README.md) for the full runbook.

```bash
make tf-init && make tf-plan      # then `make tf-apply`
```

## Roadmap

The platform (Phases 1–4) and **5a** are done. The rest of the financial pivot,
sequenced so each slice is shippable:

- **5a — Extraction + fact store + computed metrics** ✅ shipped: parsers (HTML
  built-in + Textract adapter) behind the `FinancialParser` Protocol, the fact
  mapper, the canonical metric store with cell provenance + restatement
  precedence, reconciliation invariants, the deterministic compute layer, the
  citation-faithfulness verifier, advice guardrails, `POST /metrics` + the
  metrics panel, and the offline financial eval.
- **5b — Unified querying** ✅ shipped: the NL→query planner merges verified
  figures into chat answers (metric cards + trend charts + post-stream number
  verification), and `make edgar-sync` pulls a watchlist entity's recent
  10-K/10-Q filings straight from SEC EDGAR into the metric store.
- **5c — Financial depth** ✅ shipped: entity **fiscal calendars** (offset FYEs
  like Apple's September labeled correctly; auto-detected from EDGAR), **FX
  conversion** with as-of ECB reference rates (annotated — the applied rate +
  date travel with the value, never a silent swap; `make fx-load`), **ratio
  trend series** (margin charts), **GAAP↔non-GAAP counterparts** surfaced side
  by side, and **segment revenue** extraction/querying (revenue-by-segment
  tables only — deliberately narrow).
- **5d — Scale & ops** ✅ shipped: **async multi-page Textract** (S3-based, page
  aggregation, temp-object cleanup, a page-count cost flag), a **parallel
  financial path in the SQS worker** (`<ENTITY>/<file>` keys, bounded
  concurrency), and the **review queue** — reconciliation violations persist to
  `reconciliation_issues`, served by `GET /review` and shown in the metrics
  panel's Data quality section.
- **Deferred (needs real-world corpus to build against):** footnote-aware
  querying, broad entity universe + dedup, segment beyond revenue-by-segment,
  spend dashboards beyond the page cap.

## Project layout

| Path | What |
|------|------|
| `backend/app/core/` | Shared contract: DTOs (`finance.py` = financial domain) + swappable Protocols |
| `backend/app/embeddings/`, `rerank/`, `vectorstore/`, `llm/` | Provider impls (narrative) |
| `backend/app/extraction/` | Financial parsers: built-in HTML tables + AWS Textract adapter |
| `backend/app/finance/` | Chart of accounts, deterministic metrics, verifier, guardrails, metric store |
| `backend/app/retrieval/`, `generation/`, `deps.py` | Hybrid retrieval, answer orchestration + routing, wiring |
| `backend/app/api/`, `main.py`, `feedback.py` | FastAPI routes (`/query` SSE, `/metrics`, `/feedback`, `/health`) + app |
| `backend/app/auth.py` | Google ID-token verification + the `require_user` gate |
| `backend/app/db/` | pgvector pool + SQL migrations (incl. the financial fact store) |
| `ingestion/pipeline/` | Loaders, chunking, indexer, SQS worker + `facts.py`/`reconcile.py`/`financial.py` (numeric path) |
| `eval/` | Retrieval + LLM-judge harness; `eval/financial/` = offline ground-truth figure eval |
| `frontend/` | Next.js + Tailwind chat UI + metrics panel + `Dockerfile` — streaming, citations, SSO |
| `infra/terraform/` | AWS IaC — ECS Fargate, RDS, S3→SQS, ECR, Secrets Manager |

## Cost

Claude generation dominates today; the routing layer is the primary lever — easy,
high-confidence queries go to Haiku ($1/$5 per 1M), typical to Sonnet ($3/$15), and
only low-confidence/long-context/complex queries to Opus ($5/$25). Prompt-caching the
system + retrieved-context prefix further cuts repeated-context cost. Voyage
embeddings/rerank are cheap; the AWS footprint (RDS `t4g.micro`, small Fargate tasks,
one NAT gateway) is low-tens of dollars a month at modest traffic. Textract adds a
per-page extraction cost at ingest, but only for PDF/scan documents
(`FINANCIAL_PARSER=textract`) — HTML filings ingest free via the built-in parser,
and `/metrics` queries cost nothing at all (no LLM in the path).
