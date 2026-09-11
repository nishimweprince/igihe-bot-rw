## Goal

Implement the reference plan in `KINYARWANDA_CHATBOT_PLAN.md` as a working vertical slice inside this repo (`igihe-bot-rw`), in one long-running task: fixture-driven ingest of a small approved article sample through extraction, normalization, chunking, hybrid retrieval, and grounded answer generation with citations and refusal, runnable and tested on this Mac without live network or model downloads.

## Success Criteria

- A clean `uv`-managed Python 3.12 project exists in this directory with a locked dependency set, and `uv sync` plus the full test suite pass on this Mac with no network access beyond the initial (documented) lock step.
- Ingesting the bundled WordPress fixtures produces raw snapshots, cleaned articles, versioned chunks, and both lexical and (fake/pluggable) dense indexes reproducibly, with an idempotent re-run that changes nothing.
- `POST /v1/chat` answers a Kinyarwanda question from the sample with passage-grounded text plus server-validated `sources` (id, title, date, URL), and returns the approved no-evidence response for an unanswerable question; no prompt text, stack trace, DB error, path, or model internal leaks to the client.
- Streaming events (`retrieval`, `token`, `sources`, `done`, `error`), `/health/live`, `/health/ready`, and `/v1/feedback` behave per the reference API contract, with bounded input limits, timeouts, and rate-limit hooks.
- A versioned mini eval set (factual, name-sensitive, date-sensitive, multi-article, unanswerable) runs in one command and reports Recall@5/10, MRR, citation-resolution rate, and refusal accuracy on the sample.
- No corpus, embeddings snapshot, conversation log, secret, or model artifact is committed; `.env.example` documents every setting; `docs/decision-log.md` records the deferred production decisions.

## Context And Current Facts

- Workspace root contains exactly one file, `KINYARWANDA_CHATBOT_PLAN.md` (~48 KB, updated 2026-09-11); there is no `.git`, no `package.json`, no source, and no `docs/` or `tests/` yet (verified by directory listing plus `git status` failing with "not a git repository").
- The reference plan is the binding technical baseline: RAG (no factual fine-tuning); PostgreSQL 16+ with `pgvector`, `pg_trgm`, `unaccent` as the production database; lexical search on the `simple` configuration; Python 3.12 + FastAPI + Pydantic with `uv` lockfile; local multilingual embeddings (BGE-M3 vs multilingual E5 bake-off); quantized instruction-tuned Llama via Ollama; Reciprocal Rank Fusion over ~40-60 dense plus ~40-60 lexical candidates with 5-8 evidence chunks; chunk target 350-600 embedding-tokenizer tokens with overlap only at paragraph boundaries; tokenizers must match the consuming model; ALTA Tokenizer stays an isolated experiment.
- Reference discovery inputs (planning data, not invariants): `old.igihe.com/wp-json/wp/v2/posts` reported 202,756 posts + 2,028 pages; earliest post 2010-05-18; 100-article sample median rendered HTML ~2,495 chars / mean ~3,288 chars; current demo holds 55 articles and passes full/latest-14 article text to the LLM (prototype, not retrieval).
- Reference architecture (section 5): reader browser -> reverse proxy -> frontend/chat widget -> Assistant API -> query embedding -> PostgreSQL+pgvector -> optional reranker -> evidence builder -> Ollama/Llama -> citation validator; separate systemd/cron ingestion worker path (WordPress API -> gzip raw snapshots -> cleaner/chunker -> document embedding -> PostgreSQL).
- Reference data model minimum (section 7): `articles` (wp_id PK, slug, canonical_url, status, published/modified times, original + normalized title/excerpt/body, author/category/tag ids, language, sha256, raw key, extraction version), `article_chunks` (uuid PK from article id + extraction version + index + content hash, chunk_index, heading, content + normalized copy, paragraph span, embedding + model/version, token_count, weighted `tsvector`), plus `authors/categories/tags`, `ingestion_runs`, `ingestion_failures`, `model_registry`, `evaluation_runs`, `feedback_events` (no raw user text by default).
- User decisions for this task (answered 2026-09-11): scope = working vertical slice (not scaffold-only, not full archive pipeline); dependencies = self-contained with fixtures (no live WordPress/model/service calls); verification = must run and pass on this Mac (Ubuntu artifacts alone are not acceptable).

## Constraints And Non-goals

Constraints for the single task:

- Build in place in this directory; do not create a second repository inside the task (the reference plan's provisional `igihe-rw-assistant` name is recorded as a rename/transfer question, not acted on).
- Self-contained: all tests and the demo path run with committed fixtures plus in-process fakes for embeddings, reranking, and generation; live PostgreSQL/Ollama/WordPress become optional env-selected backends with documented Compose files, never required for green tests.
- Mac-verifiable: default `pytest` path uses SQLite/FTS (or in-memory) lexical search and a deterministic fake dense index; the Postgres `tsvector`/`pgvector` SQL ships as migrations plus an integration test marked to skip without a live DB.
- One task, one working tree: ordered units below run sequentially with no cross-unit parallel writes; no commits/pushes unless the user later asks (planning creates no code).
- Privacy/secrets: never commit corpus data, embeddings, snapshots, conversations, `.env`, or model files; only small approved fixtures and summary eval reports.

Non-goals for this task (deferred to later tasks per reference sections 20-21):

- Full-archive backfill (202k posts), production HNSW build, incremental 5-15 min sync, deletion reconciliation, backups/PITR, production monitoring/alerts/runbooks.
- Embedding bake-off on 100+ editor-reviewed judgments, reranker integration, retriever fine-tuning, ALTA tokenizer benchmark beyond a stub lane.
- Production Ubuntu rollout, TLS/reverse-proxy setup, GPU inference, load-test SLO gate (k6/Locust), multilingual answers, voice, OCR, site-search replacement.

## Key Decisions

- **D1 — Build the slice in this directory.** Recommended because the workspace is empty and the user said "in this repo"; alternatives (nesting a second repo, renaming the folder mid-task) were rejected as churn with no technical gain. Record the provisional `igihe-rw-assistant` naming question in `docs/decision-log.md`.
- **D2 — Follow the reference Python baseline (3.12, FastAPI, Pydantic, `uv`).** This restates the binding workspace decision (reference section 5.2); no Next.js runtime work in this task beyond a static demo client if trivial. Rejected: introducing a second API framework or task queue.
- **D3 — Ship migrations for the production schema but verify on portable storage by default.** Migrations carry the reference tables/indexes (`tsvector` GIN, trigram, HNSW cosine) for real Postgres; the default test/demo path uses a file-backed SQLite FTS + NumPy-free fake dense store behind a `RetrievalBackend` protocol so `pytest` passes on this Mac with no containers. Rejected: requiring Docker for green tests, or skipping migrations entirely (would hide schema drift).
- **D4 — Fake the model boundaries with strict contracts.** `Embedder` (deterministic hash-vector + recorded model id/revision/dim) and `Generator` (template answer from supplied evidence + citation markers) implement the same interfaces as the later BGE/E5 and Ollama adapters; citation validation, token budgeting (via each adapter's tokenizer rule), refusal, and streaming stay real and tested. Rejected: downloading real models in this task (breaks self-contained constraint) and asserting quality thresholds that need editor review.
- **D5 — Hybrid retrieval as RRF over lexical + dense with metadata/date filters, no reranker.** This is the smallest faithful cut of reference section 11 (top-N each side, RRF merge, near-dup grouping, 5-8 evidence chunks, Africa/Kigali relative-date handling). Reranking stays a disabled interface with a skip-gated test. Rejected: dense-only or lexical-only shortcuts (would not prove the hybrid path).
- **D6 — ALTA stays out of the request path.** Keep a `tokenization/` experiment stub plus the reference safety notes (isolated container, pinned wheel hash, pickle-as-code review) documented, with no ALTA code in chunking/generation. Rejected: wiring ALTA counts into truncation (explicitly forbidden by reference section 9.3).

## Recommended Approach

Scaffold the reference monorepo layout trimmed to the slice, then walk one deterministic fixture path end to end: committed WordPress JSON fixtures (one per reference extraction case: normal, video-embed, photo-captions, opinion, short announcement, malformed legacy HTML, tables/lists, mixed Kinyarwanda/English, corrected update) -> gzip raw snapshot + manifest + `ingestion_runs` audit row -> `lxml`/Beautiful-Soup extraction (entity decode, boilerplate strip, paragraph/headings/quotes/lists/captions preserved, quarantine on empty/enormous) -> NFC normalization with separate original/search copies (no English stemming, versioned) -> article-aware chunks (short article = one chunk; sentence-boundary splits; title/category/date/heading prepended to embedded text, citable body stored separately; UUID from article id + extraction version + index + content hash; token counts from the active embedder tokenizer) -> dual index (SQLite FTS default; Postgres migration parity) -> FastAPI `/v1/chat` (validate -> normalize -> date/category filter extraction -> embed -> top-N lexical + dense -> RRF -> near-dup grouping -> evidence pack -> budgeted prompt with delimited untrusted evidence -> fake generator -> citation/URL validation -> SSE stream) -> mini eval + coverage report. Every seam (embedder, generator, retrieval backend, clock, WordPress client) is an injectable protocol so the later production swap (BGE-M3/E5, Ollama Llama, Postgres+pgvector, live WP sync) needs no API or schema redesign. Editorial/production gates from reference sections 20/23/24 (100k/day meaning, hardware sizing, model licenses, content scope, retention, reviewers, standard platform tools) are logged as deferred decisions, not resolved here.

## Work Plan

1. **Repo scaffold, config, and decision log** — `pyproject.toml` (Python 3.12, FastAPI, Pydantic, lxml/bs4, pytest/httpx), `uv.lock` generation step, `.env.example` (all reference section 16.3 keys), `docker-compose.yml` (api, postgres:16+pgvector, ollama profiles; not required for tests), `README.md`, `docs/decision-log.md` (records D1-D6 + deferred reference section-23 questions), `src/igihe_assistant/config/`. Depends on: nothing.
2. **Schema migrations + storage protocols** — `migrations/` implementing reference section-7 tables/indexes (articles, chunks, authors/categories/tags, ingestion_runs/failures, model_registry, evaluation_runs, feedback_events) plus `RetrievalBackend`/`RawStore` protocols with SQLite/file default and Postgres adapter stub. Depends on: unit 1.
3. **Ingestion worker (fixture-driven)** — WordPress client with injectable transport, `_fields` allowlist, ascending backfill with page checkpoints, `Retry-After`-aware backoff, gzip raw snapshots + sha256 manifest, `wp_id`-idempotent upsert, overlap-window incremental stub, quarantine path. Ships `tests/fixtures/wp/*.json` (9 extraction cases) and coverage/failure report script. Depends on: units 1-2.
4. **Extraction + normalization** — parser and NFC/whitespace/quote normalizer producing paired original/search copies, content hash, regression snapshot tests per fixture, malformed-content quarantine tests. Depends on: unit 3 fixtures.
5. **Chunking + indexing** — article-aware chunker (350-600 token target via embedder tokenizer, sentence boundaries, metadata prepending, stable UUIDs) plus dual indexing (FTS default, Postgres SQL parity) and versioned embedding records. Depends on: units 2-4.
6. **Hybrid retrieval API core** — query validation/normalization, explicit date/category filters (Africa/Kigali relatives), dual top-N fetch, RRF merge, near-dup grouping, 5-8 chunk selection under token budget, deterministic fake embedder; unit tests for RRF weighting, filter behavior, and grouping. Depends on: unit 5.
7. **Generation, validation, and HTTP contract** — prompt builder (Kinyarwanda default, delimited untrusted evidence, `[n]` citations, publication-vs-event date rule), fake generator, citation/URL validator, SSE streaming (`retrieval/token/sources/done/error`), `/health/live`, `/health/ready`, `/v1/sources/{article_id}`, `/v1/feedback` (no raw text), body/token/concurrency limits, timeouts, rate-limit hooks. Depends on: unit 6.
8. **Mini eval + docs + smoke** — `evals/datasets/mini-v1.jsonl` (factual, name, date, multi-article, unanswerable), one-command runner reporting Recall@5/10, MRR, citation-resolution rate, refusal accuracy; `scripts/smoke.sh` (sync, migrate, ingest fixtures, serve, chat + refusal probes); README quickstart and deferred-gate list. Depends on: units 1-7.

## Validation Plan

- `uv sync && uv run pytest -q` — full suite green offline on this Mac (Postgres/Ollama integration tests skip without services; expected evidence: `N passed, M skipped, 0 failed`).
- `uv run ruff check src apps tests` (or configured lint) — clean.
- Fixture determinism: run `uv run python scripts/ingest_fixtures.py --sample tests/fixtures/wp && uv run python scripts/ingest_fixtures.py --sample tests/fixtures/wp` twice and `diff` manifests/chunk hashes — byte-identical second run, zero new writes.
- API contract (against local uvicorn): `GET /health/live` -> 200 `{"status":"ok"}`; `GET /health/ready` -> 200 with backend flags in fixture mode; `POST /v1/chat` factual probe -> 200 SSE containing `sources` event with resolvable article IDs/URLs and `[n]` markers in `token` text; `POST /v1/chat` unanswerable probe -> approved no-evidence Kinyarwanda wording with zero citations; oversized payload -> 413; malformed citation injection fixture -> validator rejects or remaps, never emits an unindexed URL.
- `uv run python evals/run_mini.py --dataset evals/datasets/mini-v1.jsonl` — prints Recall@5/10, MRR, citation-resolution %, refusal % on the sample (no fixed threshold gate in this task; numbers are recorded as the baseline for the later editor-reviewed set).
- Highest-risk step: the live-contract SSE probe above (retrieval -> generation -> citation validation); if streaming and citation mapping disagree, nothing else in the slice counts as done.

## Risks / Rollback

- **Single-task size**: the slice is deliberately fixture-scale; if the task overruns, cut in this order: feedback endpoint polish, static demo client, Postgres parity test — never the refusal path or citation validator.
- **No version control yet**: directory is not a git repo; rollback is deleting generated `uv.lock`, `.venv`, `data/`, and `dist/` outputs — no live system is touched. Recommend `git init` plus an initial commit before the task starts (outside this plan's scope until approved).
- **Fake-model overconfidence**: fake embedder/generator prove plumbing only; risk is mitigated by adapter protocols, recorded model ids, and an explicit "not a quality gate" label on mini-eval numbers.
- **Portability drift**: SQLite FTS is a stand-in, not the production index; mitigation is shipping real Postgres migrations plus a skip-gated parity test so drift is visible.
- **Reference-plan divergence**: any deviation from `KINYARWANDA_CHATBOT_PLAN.md` (schema, contract, retention) must be logged in `docs/decision-log.md` with reason; unresolved production decisions stay deferred, never silently decided.

## Open Questions

None. All remaining production questions from reference section 23 (100k/day meaning, Ubuntu sizing, approved Llama variants/licenses, GPU fallback, content scope, second-site ingest, frontend/auth conventions, snapshot/log retention, reviewers and no-evidence wording authority, standard platform/secret/backup tooling) are intentionally deferred to `docs/decision-log.md` in unit 1 and do not block this self-contained slice.
