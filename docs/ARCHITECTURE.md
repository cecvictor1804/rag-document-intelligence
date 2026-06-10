# System Architecture & Tradeoff Report

Covers the system as built through Phase 5d + CI. Every section states what was
chosen, what it was chosen over, why, and what cost was accepted.

---

## 1. The Macro-Architecture: Two Substrates Under One Surface

**Chosen:** a *narrative substrate* (classic RAG: chunks → embeddings → hybrid
retrieval → LLM with citations) and a *numeric substrate* (parsed tables →
normalized fact store → deterministic compute), merged at answer time by a
planner.

**Over:** (a) pure RAG with better prompting, (b) a single "everything is
structured data" system, (c) an agentic LLM with tools.

**Why:** financial questions split cleanly into two failure regimes. Narrative
questions ("why did margins fall?") need retrieval and synthesis — structure
adds nothing. Numeric questions ("what was Q3 gross margin?") fail
catastrophically under RAG: tables flatten into word-soup, the LLM transcribes
or computes numbers wrong, and the error is *confident*. Splitting substrates
lets each be held to its appropriate standard — fuzzy-but-grounded for prose,
exact-or-absent for numbers.

**Cost accepted:** two pipelines to maintain, a merge layer (planner +
verification) that is itself a component with failure modes, and double
ingestion of the same document (chunked for prose, parsed for tables). We
judged the duplication cheaper than the alternative: a single pipeline that is
mediocre at both jobs.

---

## 2. Backend Platform

### 2.1 Python 3.12 + FastAPI

**Over:** Node/TypeScript end-to-end, Go, Django.

**Why:** the AI/data ecosystem (anthropic, voyageai, psycopg, boto3, bs4) is
Python-native; FastAPI gives async SSE streaming, Pydantic validation at the
boundary, and — decisively — **dependency injection via `Depends`**, which
became the test seam for the whole API surface (`app.dependency_overrides`
lets every route test run without a DB or API keys).

**Cost:** a polyglot repo (Python backend, TS frontend) with two toolchains,
two test runners, two lint stacks. CI runs them as parallel jobs, so the cost
is configuration, not wall-clock.

### 2.2 Plain dataclasses for the core domain, Pydantic only at the HTTP edge

**Over:** Pydantic models everywhere.

**Why:** ingestion constructs millions of `Chunk`/`FinancialFact` objects in
tight loops; `@dataclass(slots=True)` is markedly cheaper than Pydantic
validation per-instance. Validation belongs at trust boundaries (HTTP
requests), not between internal functions that share a type system.

**Cost:** no runtime validation internally — a bug can put a malformed fact in
the store. Mitigated by mypy strictness and the reconciliation invariants,
which catch *semantic* corruption (the kind type checks can't).

### 2.3 Protocol-based seams

(`EmbeddingProvider`, `Reranker`, `VectorStore`, `LLMClient`,
`FinancialParser`, `MetricStore`, `QueryPlanner`)

**Over:** direct vendor imports, or a heavyweight plugin framework.

**Why:** every external dependency — and every expensive internal one — sits
behind a `typing.Protocol`, selected once in the composition root (`deps.py`).
This bought three things: (1) vendor swaps are config changes (proven when
Textract was added beside the HTML parser); (2) the entire test suite (140
backend tests) runs offline against in-memory fakes; (3) the eval harness
reuses production code with a fake store, making the ground-truth eval free of
infrastructure.

**Cost:** indirection. Every feature touches an interface, an implementation,
a factory, and a fake. For a solo project this is real overhead per change; it
paid for itself by roughly Phase 2 and compounded after.

---

## 3. Data Layer

### 3.1 Postgres + pgvector as the *only* database

**Over:** a managed vector DB (Pinecone/Weaviate/Qdrant) beside Postgres; or
OpenSearch for lexical.

**Why:** one database holds the vectors (pgvector HNSW), the lexical index
(generated `tsvector` column), the financial fact store, feedback, query logs,
FX rates, and the review queue. That means one connection pool, one migration
system, one backup story, one Terraform resource — and crucially, **joins
between worlds** (the authoritative-facts view joins facts to documents for
precedence; review issues join to entities). A managed vector DB would shave
latency at scale we don't have, at the price of a second system and no joins.

**Cost:** pgvector HNSW is weaker than dedicated engines at very large corpora
(>10M vectors) and Postgres becomes the single point of contention. The
`VectorStore` Protocol is the explicit escape hatch; the cost today is zero,
the migration path is preserved.

### 3.2 Generated `tsvector` column for lexical search

**Over:** Elasticsearch/OpenSearch; application-side BM25.

**Why:** `GENERATED ALWAYS AS (to_tsvector(...)) STORED` means the lexical
index *cannot* drift from the text — no dual-write bug class at all. Good
enough relevance for a corpus of internal docs and filings.

**Cost:** Postgres FTS ranking (ts_rank) is cruder than BM25 with tuned
analyzers. The reranker was chosen partly to compensate: fusion candidates only
need to be *recalled*, not perfectly ranked, because rerank-2 re-orders the
top ~40 anyway.

### 3.3 Idempotency via content hashes (doc-level + chunk-level)

**Over:** timestamps/etags; full re-index on change.

**Why:** re-ingestion compares sha256 of content — unchanged docs are skipped
entirely, changed docs re-embed only changed chunks, and deleted docs are
pruned by set difference. Embeddings are the dominant ingest cost; hashing
makes re-runs nearly free and makes the pipeline safe to run blindly (cron,
worker retries, manual re-runs).

**Cost:** any change to chunking parameters silently invalidates nothing
(hashes change → full re-embed), which is correct but surprising; and hash
comparison requires fetching/extracting text even for unchanged docs (loaders
run; only embedding is skipped).

---

## 4. Retrieval & Generation (Narrative Substrate)

### 4.1 Hybrid retrieval: dense HNSW + lexical, fused with RRF

**Over:** dense-only; lexical-only; weighted score blending.

**Why:** dense misses exact identifiers (ticker symbols, policy numbers,
"10-K/A"); lexical misses paraphrase. RRF (Reciprocal Rank Fusion) was chosen
over score blending for one decisive property: it is **calibration-free**.
Cosine similarities and ts_rank live on incomparable scales; any weighted blend
needs tuning that goes stale. RRF uses only ranks — `Σ 1/(k+rank)` — and is
robust to either retriever being garbage on a given query.

**Cost:** RRF discards score magnitude — a dense hit at 0.95 and one at 0.55
in the same rank position contribute equally. The reranker downstream restores
fine-grained ordering, which is exactly why fusion feeds *40* candidates to a
reranker that keeps *8*.

### 4.2 Cross-encoder reranking (Voyage rerank-2)

**Over:** trusting fusion order; an LLM-as-reranker.

**Why:** a cross-encoder reads query and passage *together* — categorically
better relevance than bi-encoder cosine. It also produces the system's single
most load-bearing scalar: the **top rerank score**, which drives both the
"I don't know" gate and the model router. One API call buys relevance,
honesty, and cost-routing signal.

**Cost:** an extra network hop (~100–300ms) and vendor dependency on every
query; the `MIN_RERANK_SCORE=0.3` threshold is empirical and corpus-sensitive.

### 4.3 Embeddings/rerank: Voyage

**Over:** OpenAI embeddings, Cohere.

**Why:** strong retrieval-tuned quality (voyage-3 at 1024 dims), a matched
reranker from the same vendor, cheap. The `openai` extra exists behind the
Protocol; the choice is one env var, which is the honest answer to "embedding
model choice" — it should be a config decision, not an architecture.

**Cost:** vendor risk; embedding dim is baked into the table schema
(`vector(1024)`), so switching to a different-dimensional model is a
migration + full re-embed, not just a config flip.

### 4.4 Cost-aware model routing (Haiku → Sonnet → Opus)

**Over:** one fixed model; user-selectable model.

**Why:** retrieval confidence is a *free* difficulty signal. High top-score →
the answer is sitting in a passage → Haiku ($1/$5 per MTok) transcribes it
fine. Low confidence or long context → Opus ($5/$25). The router is a pure
function of (top score, context tokens, query length) — deterministic,
loggable (`query_log` records every decision), and re-tunable from data.
Generation dominates system cost, so this is *the* primary cost lever.

**Cost:** a misroute sends a subtle question to Haiku. The thresholds
(0.65/0.45) encode a bet that retrieval confidence correlates with generation
difficulty — mostly true, not always. The query log exists precisely to audit
this.

**Sub-decision — per-tier request kwargs (`_tier_kwargs`):** the Anthropic API
rejects parameters unsupported by a tier (effort on Haiku → 400). Gating
kwargs by model family in one function was chosen over a capability-discovery
call for simplicity; cost is a table to maintain when models change.

### 4.5 The "I don't know" gate (min rerank score short-circuit)

**Over:** always answering; letting the LLM decide.

**Why:** if the best passage scores below threshold, the system returns a
canned refusal **without calling Claude**. This prevents the worst RAG failure
(fluent hallucination on out-of-corpus questions) *and* saves the model call.
LLM self-assessment of "do I know this?" is unreliable; a retrieval score is a
better-calibrated, free signal. Phase 5b refined it: verified figures can
carry an answer even when prose retrieval is weak.

**Cost:** false refusals when relevant content exists but scores poorly
(vocabulary mismatch). Tunable, observable via logs.

### 4.6 SSE streaming end-to-end

**Over:** request/response JSON; WebSockets.

**Why:** answers take seconds; perceived latency is the UX. SSE is
unidirectional (all we need), survives proxies, and maps 1:1 onto the internal
event model (`meta`/`token`/`metrics`/`series`/`citations`/`verification`/
`done`) — the typed event enum is the *contract* between backend and frontend,
mirrored in TypeScript. WebSockets would buy bidirectionality nobody needs at
the price of connection management and worse infra compatibility.

**Cost:** EventSource can't POST, so the frontend hand-parses the SSE stream
from `fetch` (a custom parser handling CRLF and split-chunk reassembly — ~60
lines that needed real tests). Also: anything already streamed cannot be
retracted, which directly shaped the verification design (§7.5).

### 4.7 Citations as inline `[n]` markers resolved post-hoc

**Over:** structured citation output (JSON schema); span-level attribution.

**Why:** the model cites naturally inline; a regex resolves markers against
the numbered context after streaming. Zero token overhead, robust to partial
output, and only markers the model *actually used* become citations.

**Cost:** marker-level granularity (passage, not sentence); a model could cite
decoratively. The faithfulness verifier (numbers) and the judge eval
(groundedness) backstop this.

---

## 5. Identity & Security

### 5.1 BFF pattern: browser → Next.js only; backend never public

**Over:** SPA calling the API directly with CORS.

**Why:** the Next.js server is the single OAuth client and the single place
secrets live; the FastAPI backend sits on a private network (ECS Service
Connect). No CORS surface at all, and the proxy seam was built in Phase 3a
explicitly so auth could be added in 3b without re-architecting — which is
exactly what happened.

**Cost:** every byte streams through two hops (backend → Next → browser);
pass-through `ReadableStream` piping keeps this cheap but it's still a hop.

### 5.2 Hand-rolled OIDC (jose + PKCE + encrypted cookie) instead of Auth.js

**Over:** NextAuth/Auth.js v5, Clerk/Auth0.

**Why:** at build time, Auth.js v5 was beta *and* its integration leaned on
the middleware surface that Next.js 16 had just renamed (`middleware` →
`proxy`) — a real compatibility risk in exactly the layer that gates every
request. The bundled Next 16 docs themselves recommend the jose + cookies
pattern. Hand-rolling the authorization-code+PKCE flow is ~300 lines, fully
unit-testable, with zero beta dependencies. Hosted providers were rejected for
an internal tool that already has a Google Workspace tenant — they add a
vendor and a bill to solve a problem Google already solves.

**Cost:** we own session security (JWE A256GCM cookie, state/nonce/PKCE
correctness, refresh logic) forever. That's a maintenance liability a library
would absorb. Mitigation: the surface is small, conservative (HttpOnly,
SameSite=Lax, encrypted not just signed — the cookie holds tokens), and tested
against RFC 7636 vectors.

### 5.3 Backend independently verifies the Google ID token (zero trust between tiers)

**Over:** backend trusting a header from the proxy; a shared-secret internal
JWT minted by Next.

**Why:** the FastAPI service verifies signature/audience/issuer/`hd` itself
via `google-auth` on *every* request. There is **no shared secret between
tiers** — compromise of the frontend doesn't grant API access, and the backend
is secure even if someone exposes it accidentally.

**Cost:** Google ID tokens expire hourly → the BFF must transparently refresh
(refresh-token flow + cookie re-issue inside streaming responses — genuinely
fiddly code). Also a certificate-fetch dependency on Google availability
(cached by the transport).

### 5.4 `AUTH_ENABLED=false` as the default

**Over:** auth always-on.

**Why:** the entire dev/test/CI loop runs with zero Google credentials;
flipping one flag (on both tiers) arms the full gate. The dual-flag
requirement is deliberate — the backend must be told to enforce, so the
frontend can't accidentally be the only lock.

**Cost:** a deployment that forgets the flag runs open. Mitigated by Terraform
wiring `auth_enabled` as a single variable feeding both services.

---

## 6. Frontend

### 6.1 Next.js 16 App Router + Tailwind v4 + hand-written shadcn-style primitives

**Over:** Vite SPA; component libraries (MUI/Mantine); actual shadcn CLI.

**Why:** Next gives the BFF (route handlers as the proxy/auth seam) — a SPA
can't be the confidential OAuth client. Tailwind v4's CSS-variable theming
made adaptive light/dark nearly free. The shadcn *style* (cva variants,
copied-in primitives) was kept but the components were written by hand — the
result is ~5 small files we fully own, which has held up fine.

**Cost:** Next 16 was new enough that prior-version knowledge was wrong
(middleware→proxy rename, async request APIs); the discipline of reading the
bundled docs before writing was mandatory. Hand-written primitives mean no
upstream fixes.

### 6.2 recharts for trend charts

**Over:** visx, hand-rolled SVG, Chart.js.

**Why:** declarative React API, themable via the existing CSS variables, one
dependency for one component. Charts here render ≤8 points — any library is
overkill; recharts was the lowest-integration-cost adequate choice.

**Cost:** ~100KB to the bundle for a small feature; fine for an internal tool.

### 6.3 Decimal-as-string across the API; float-free formatting

**Over:** JSON numbers.

**Why:** money in general doesn't survive JSON floats (precision, trailing
digits), and the system's core promise is exactness. Every monetary value
crosses the wire as a string; the frontend formatter compacts magnitudes
("$94.93B") by *string slicing*, not float math. Floats appear exactly once —
chart point geometry, where pixel positions don't need exactness.

**Cost:** typing friction (`value: string` everywhere) and custom formatting
code instead of `toLocaleString`. Accepted as the price of the
no-wrong-numbers invariant.

---

## 7. The Financial Layer

### 7.1 Canonical metric store (normalized facts)

**Over:** (a) facts attached to RAG chunks as metadata; (b) per-document table
blobs; (c) on-demand vision-model table reading at query time.

**Why:** computation (YoY, ratios), cross-period alignment, and conflict
resolution all require facts to be *addressable independently of their
documents*. Chunk-attached facts make "revenue across 8 quarters" a retrieval
problem again; query-time vision reading makes every numeric answer slow,
expensive, and non-deterministic. The normalized store makes them an indexed
SQL lookup.

**Cost:** the highest-engineering-cost option — schema, mapper, precedence
model, its own eval. This was the single biggest bet in the design interview,
taken knowingly.

**Sub-decisions inside the fact row:**
- **Normalized base value AND as-reported value/scale/currency both stored.**
  Lossless: computation uses base units; provenance display shows what was
  printed ("94,930 ×10⁶"). Storing only one loses either correctness or
  auditability.
- **`Decimal`/`NUMERIC` end-to-end.** Floats never touch a reported figure.
  Non-negotiable given the domain; costs only ergonomics.
- **Cell-level provenance (`page/table/row/col`) on every fact.** The unit of
  trust. Costs four columns; buys drill-down, the verification chain, and
  audit defensibility.

### 7.2 Hybrid canonical + as-reported line items

**Over:** full US-GAAP taxonomy mapping; as-reported only.

**Why:** companies say "Net sales", "Total revenues", "Revenue, net" for the
same concept — without canonicalization, cross-period/cross-company queries
die. But a full taxonomy mapping is a permanently-unfinished project, and
*wrong* mappings are worse than none. So: a curated ~24-concept chart (named
after us-gaap concepts for future XBRL alignment), **exact-normalized-synonym
matching only**, and the company's own label is *always* preserved on the
fact. Unmapped facts still exist and are queryable by their as-reported label.

**Cost:** conservative matching means real synonyms get missed until added (a
curation treadmill). Chosen deliberately: a missed mapping degrades to "no
data"; a wrong mapping produces a wrong number with a confident citation.

### 7.3 Conflict resolution: authority-rank + recency precedence, alternates kept

**Over:** latest-document-wins; surface-all-conflicts-to-the-user.

**Why:** finance has a *real* authority ordering: amendment (10-K/A) > audited
annual > quarterly > press release. The `authoritative_facts` view picks one
winner per (entity, concept, segment, basis, period) by
`authority DESC, filed_date DESC` — restatements automatically supersede —
while **alternates remain queryable** in the base table. Latest-wins is wrong
(a press release postdating a 10-K shouldn't beat it); always-asking-the-user
makes every metric query a chore.

**Cost:** the precedence ranking is policy baked into a SQL view — auditable
and changeable, but opinionated. Edge cases (two same-rank docs same day) fall
to insertion order.

### 7.4 Deterministic compute layer

**Over:** LLM in-context arithmetic; LLM + calculator tool-use.

**Why:** margins, YoY, ratios are *pure functions*; code computes them
exactly, unit-testably, and every `MetricResult` carries its input facts (with
cells) so derived numbers inherit provenance. Tool-use gets you correct
arithmetic but non-deterministic *orchestration* (which numbers, which
periods) and an audit story that's "read the transcript". LLM freehand math is
disqualified outright in this domain.

**Cost:** only registered metrics are computable — a long-tail analyst formula
("R&D as % of gross profit") isn't, until added to the registry. The registry
is the rigidity we accepted for trust; arbitrary-formula support
(LLM-composed but code-executed) is a known future direction.

**Sub-decision:** `MetricError` on *incomparable inputs* — mixed
currency/period/basis/entity raises rather than computes. Silent unit mixing
is the classic catastrophic spreadsheet bug; we made it structurally
impossible.

### 7.5 Number trust: post-stream verification that flags, never silently passes

**Over:** (a) blocking the stream until verified; (b) structured
"extract-then-narrate" answers; (c) trusting the prompt.

**Why:** the chain is: verified figures injected into the prompt ("use
verbatim") → model narrates → after the stream, every numeric token in the
answer is parsed (handling "$94.9 billion", "94,930 million", percents,
rounding) and matched against allowed values (metric results + numbers present
in retrieved passages) → unmatched numbers are flagged in the UI. Once you
commit to streaming (§4.6), you *cannot* suppress what's already shown —
flagging is the honest mechanism. Extract-then-narrate (the model only fills
slots) gives a stronger guarantee but kills answer fluency and was reserved as
a fallback posture.

**Cost:** flagging is post-hoc — a wrong number is visible for the seconds
before the flag appears. And the matcher's tolerance windows (rounding, scale
renditions) trade false-flags against missed-fabrications; we tuned
conservative (flag when unsure) because a false flag costs a glance, a missed
fabrication costs trust.

### 7.6 The NL→query planner: one cheap constrained call

**Over:** agentic tool-use loop; keyword/intent router; no planner (separate
metric UI only).

**Why:** a single Haiku-tier call maps the question to
`{entity, requests[{metric, period, series, segment}]}` where `metric` **must
come from the enumerated legal vocabulary** — the planner can *select*
figures, never *invent* them, and never produces a number itself. Execution is
then 100% deterministic. An agentic loop is more flexible (multi-hop
questions) but unbounded in cost/latency and far harder to audit; a keyword
router can't extract periods/segments reliably; planner-less means numbers
never reach the chat.

**Failure posture (a choice in itself):** *any* planner failure — transport
error, malformed JSON, unknown metric, missing entity — yields `None`, and the
system degrades to plain narrative RAG. The feature can only add, never break.
`PLANNER_ENABLED=false` removes it entirely.

**Sub-decision — prompt-JSON over the structured-outputs API:** strict
JSON-only prompting + defensive parsing (regex extraction, vocabulary
filtering) was chosen because the parse already had to be defensive
(vocabulary check), the failure mode is identical (degrade to None), and it
removed an unverifiable-in-the-build-environment API surface. Structured
outputs remain the documented upgrade path.

**Cost:** +1 model call (~$0.0005, ~300ms) per chat question; single-shot
planning can't decompose multi-hop questions — the narrating model handles
comparison reasoning from the verified figures block.

### 7.7 Advice guardrails: deterministic pre-gate + prompt, defense in depth

**Over:** prompt-only; an LLM classifier.

**Why:** regex patterns catch "should I buy/sell", "price target", "good
investment" *before any retrieval or model call* — free, fast, unbypassable by
prompt injection in retrieved content. The system prompt independently forbids
advice for phrasings that slip the patterns. An LLM classifier would catch
more paraphrase but adds a call to every query and is itself promptable.

**Cost:** regex is crude — adversarial phrasing gets through to the
prompt-level defense; over-broad patterns could refuse legitimate analysis.
Patterns were tested against both classes.

### 7.8 Table extraction: built-in HTML parser + AWS Textract behind one Protocol

**Over:** specialist financial-parsing vendors; vision-LLM extraction;
one-parser-fits-all.

**Why, HTML-built-in:** SEC EDGAR filings *are* HTML — `<table>` grids with
captions are parseable with BeautifulSoup at zero per-page cost. The
caption-association logic (nearest preceding heading + scale note, never
crossing a previous table) is where filings declare "(In millions)" — the
single highest-stakes context detection in the pipeline.

**Why Textract for PDF/scans:** the deployment is already AWS, so documents
**stay in-account** (data residency), auth is IAM roles not another vendor
key, and boto3 was already a dependency. A specialist vendor may win on
merged-header accuracy; the Protocol makes that swap a config change if
accuracy data ever demands it.

**Honest limitations, by design:** colspan/rowspan not expanded; split
`$`-cells parse as no-value; non-HTML rejected by the HTML parser *rather than
mis-parsed* — every limitation degrades to "missing fact", never "wrong fact".
Async multi-page Textract (S3 upload → start → poll → paginate → guaranteed
cleanup) is gated by a page-count cost flag rather than hard refusal (a hard
cap post-analysis would waste the spend already incurred).

### 7.9 Reconciliation invariants + human review queue

**Over:** trusting extraction; hard-rejecting unbalanced documents.

**Why:** filings assert their own checksums — Assets = Liabilities + Equity,
Revenue − CoR = Gross profit. Violations (beyond a 0.5% rounding tolerance,
magnitudes used so both cost-sign conventions reconcile) **flag the document
but still store the facts**: a violation usually means *one* bad cell, and
discarding 21 good facts over it is worse. Flags persist to
`reconciliation_issues`, surface via `GET /review` and the panel's Data
quality section — the human-in-the-loop seam, chosen over auto-rejection
because extraction confidence is not binary.

**Cost:** flagged-but-stored facts are servable before a human looks. The flag
travels with the doc, not the individual fact — fact-level quarantine is a
known refinement.

### 7.10 Fiscal calendars, FX, segments — the depth choices

- **Fiscal calendars:** period labels computed from the entity's FYE month
  (`fiscal_year = end.year if month ≤ fye else +1`), **auto-detected from
  EDGAR's `fiscalYearEnd`**. Chosen over calendar-only (silently mislabels
  Apple by a quarter — a *wrong-but-confident* answer) and over per-document
  inference (headers don't state the fiscal convention). Default 12 reproduces
  calendar behavior exactly. Cost: entity-level config that can be wrong for
  odd calendars (53-week years approximate).
- **FX:** ECB EUR-based reference rates, cross rates derived via EUR,
  nearest-rate-≤-date lookup; conversion returned as an **annotated
  companion** (`converted: {value, rate, rate_date}`) — never replacing the
  as-reported figure. Chosen over a commercial FX API (cost, key management)
  and over silent conversion (an invisible rate is an invisible error source).
  Cost: reference rates are daily/indicative, not transaction-grade — fine for
  analyst context, stated as such.
- **Segments:** extraction *only* from revenue-by-segment tables
  (caption-gated), rows → segment-tagged revenue facts. Chosen over general
  segment-matrix parsing, which is layout-chaotic and would violate the
  "missing, never wrong" rule. The narrow slice covers the most common analyst
  ask ("Services revenue?").

### 7.11 The offline financial eval

**Over:** DB-backed eval; LLM-judge for numbers.

**Why:** the eval pushes the *real* sample filing through the *real* parser →
mapper → in-memory store → compute, and asserts **exact** expected values (15
figures), reconciliation cleanliness, and verifier behavior (correct narration
passes, corrupted narration is flagged). Because it needs no DB and no API
keys, it runs in CI on every push — extraction exactness is a *merge gate*,
not a dashboard. An LLM judge for numeric accuracy was rejected: judging
exactness with a probabilistic model is a category error.

**Cost:** ground truth is one synthetic filing — clean HTML, friendly layout.
Real-filing fixtures are the obvious hardening step; the harness is built for
it (add files + cases).

---

## 8. Ingestion Topology

### 8.1 S3 → SQS → long-polling worker

**Over:** Lambda triggers; periodic full re-scans.

**Why:** S3 event notifications give incremental, event-driven indexing; SQS
gives buffering, retry (leave-on-failure → redelivery), and a DLQ. A
long-running worker was chosen over Lambda because ingestion holds warm
clients (embedder, parser, DB pool) and financial extraction can exceed
Lambda's comfort zone; the worker is also the same container image as the API
(one image, three commands — API/worker/migrate), which keeps the deploy
surface minimal.

**Cost:** a continuously-running task costs money idle (one small Fargate
task); Lambda would scale to zero. At watchlist volumes the fixed cost is
trivially small.

### 8.2 `<ENTITY>/<file>` S3 key convention for the financial path

**Over:** entity metadata in S3 object tags; a registration API.

**Why:** the worker must know which entity a dropped filing belongs to; a path
convention is zero-API, human-legible in the console, and trivially testable.
Keys without a folder simply skip the financial path (narrative-only) —
graceful by default.

**Cost:** conventions are unenforced — a typo'd folder creates a new entity.
Acceptable for an internal watchlist; tags or a manifest would harden it.

### 8.3 EDGAR watchlist feed

**Over:** a commercial filings API; manual upload only.

**Why:** EDGAR's submissions API is free, authoritative, and returns exactly
what the precedence model needs (form type, filed date, `fiscalYearEnd`) —
metadata that's *more* reliable than filename inference. The required
descriptive User-Agent is enforced in code (refuses to run without it) out of
respect for SEC's fair-access policy. Downloads cache to disk so the same
files feed the narrative indexer.

**Cost:** EDGAR-only (no foreign filings, no press-release wires); polling not
push. A commercial API solves both for money — deferred until the need is
real.

### 8.4 Worker concurrency: bounded semaphore, narrative batched

**Over:** unbounded `gather`; strict serial processing.

**Why:** financial extraction is per-document and independent → parallel under
`Semaphore(WORKER_CONCURRENCY=4)`; one bad document logs and continues
(per-key try/except), never poisoning the batch. Narrative indexing stays
batched because the indexer already batches embeddings efficiently.

**Cost:** bounded parallelism is still a fixed knob, not autoscaling;
"near-real-time" is minutes under burst, not seconds. True elastic extraction
(fan-out to tasks) is the known next rung.

---

## 9. Infrastructure

### 9.1 ECS Fargate for everything

**Over:** App Runner; EKS; Lambda.

**Why:** the deciding constraint was the **worker** — a long-polling SQS
consumer with no HTTP surface, which App Runner cannot run. Once one service
needs ECS, running all three (frontend, backend, worker) as one uniform
pattern (cluster + task def + service ×3) beats mixing compute models. EKS is
operational overkill for three services; serverless fails the worker and the
warm-client profile.

**Cost:** vs App Runner, we own the ALB, target groups, health checks, and VPC
wiring — roughly +400 lines of Terraform. Uniformity was judged worth it.

### 9.2 ECS Service Connect for frontend→backend, single public ALB

**Over:** an internal ALB; public backend with auth.

**Why:** only the frontend is internet-facing; the backend resolves as
`http://backend:8000` over the service mesh namespace. This deletes an entire
load balancer (≈$16/mo + config) and removes the backend from the attack
surface entirely — even though the backend *also* independently verifies
tokens (§5.3), layered.

**Cost:** Service Connect is ECS-specific (mild lock-in) and adds a sidecar
per task (small memory overhead).

### 9.3 Single NAT, single backend image, composed `DATABASE_URL` secret

Three small choices with the same shape — **simplicity over redundancy at this
scale**:
- One NAT (≈$32/mo) instead of per-AZ: an AZ outage degrades egress;
  acceptable for an internal tool, and the NAT is already the cost floor.
- One backend image serving API/worker/migrate via different commands: one ECR
  repo, one build, no drift between API and worker code versions.
- Terraform composes `postgresql://user:pass@host/db` into a single Secrets
  Manager secret so the *application contract* (one `DATABASE_URL` env var)
  needed zero code changes for AWS.

**Cost of the last:** secret values transit Terraform state — explicitly
documented, with the encrypted-S3-backend stub provided as the mitigation.

### 9.4 Plain Terraform resources (+ the VPC community module only)

**Over:** heavy module composition; CDK/Pulumi.

**Why:** the VPC module earns its abstraction (subnet math, route tables);
everything else is plain `aws_*` resources, which keeps the mental model "read
the file, see the infrastructure." HCL over CDK because declarative state
diffing is the core value and a small team doesn't need a programming language
for 16 files.

**Cost:** repetition across the three ECS services (accepted; a `for_each`
refactor is mechanical if a fourth service appears). And honestly: authored
without local terraform tooling — which is exactly why CI runs
`terraform validate` as its own job (non-blocking until first green, then a
hard gate).

---

## 10. Quality Infrastructure

### 10.1 Testing: fakes at Protocol seams, zero mocking frameworks

**Over:** mock/patch-heavy tests; integration tests against containers.

**Why:** every Protocol has a hand-written fake (`FakeLLM`, `FakeRetrieval`,
`RecordingStore`, fake Textract/S3/EDGAR transports). 140 backend + 24
frontend tests run in seconds with no DB, no network, no keys — which is *why*
the suite actually gets run on every change. Hand-written fakes over
`unittest.mock` because fakes encode behavioral contracts (a recording store
*accumulates*; a fake transport *returns fixtures*) rather than brittle
call-signature assertions.

**Cost:** the Postgres implementations (`PgMetricStore`, SQL views,
migrations) are *not* covered by unit tests — the authoritative-facts
precedence SQL is verified only by inspection and gets its first real exercise
at deploy. A testcontainers layer is the known gap.

### 10.2 CI as the same gate as local

**Why:** the workflow runs literally the same commands documented in the
README (`ruff`/`mypy`/`pytest`/`eval.financial`; `typecheck`/`vitest`/`build`;
`terraform validate`) — no CI-special scripts to drift. The financial eval in
CI is the distinctive choice: **numeric exactness is a merge gate**.

---

## 11. The Two Meta-Decisions

Two postures recur through every component and are worth naming as
architecture:

1. **Degrade, never break; missing, never wrong.** The planner fails →
   narrative answer. The parser can't handle a format → rejection, not
   mis-parse. A label doesn't match → unmapped fact, not mis-mapped.
   Reconciliation fails → flag, not silent storage *or* silent discard. Every
   component has an explicit, tested failure posture, and every posture errs
   toward *absence of information* over *wrong information* — because in this
   domain, "no answer" costs a follow-up while "wrong number" costs trust
   permanently.

2. **Provenance is load-bearing, not decorative.** Cell refs, as-reported
   values, applied FX rates, authority ranks, verification flags — every
   transformation a number undergoes is recorded *next to the number* and
   surfaced in the UI. The system's claim is not "the numbers are right" but
   the stronger, checkable claim: "here is exactly where every number came
   from."
