# IGIHE Kinyarwanda News Assistant

Grounded Kinyarwanda Q&A over the full IGIHE archive (~200k articles):
WordPress JSON -> extraction -> chunking -> **SQLite FTS5 trigram index**
(character n-grams handle Kinyarwanda inflection with no ML) -> recency-aware
BM25 ranking with a coverage gate -> **Gemma 4 E2B on MLX** (or OpenAI /
Ollama, explicit opt-in) -> short cited answer streamed token by token, with
server-side citation validation that replaces anything uncited by a refusal.

## Quickstart (tests, fixtures, no model)

```sh
uv sync --extra dev
uv run pytest -q
uv run uvicorn apps.api.main:app --port 8000   # GENERATOR=fake, 9 fixture articles
```

## Full corpus + local model (this Mac, 8 GB)

```sh
uv sync --extra dev --extra mlx
# 1. one-time: build the persistent index from the fetched archive (~5 min, ~3.1 GB)
uv run python scripts/build_index.py --pages data/full/pages --out data/index/full.sqlite
# 2. check the checkpoint loads and answers with a citation
uv run python scripts/mlx_smoke.py
# 3. serve (config comes from .env; plain `uv run` won't load it)
uv run --env-file .env uvicorn apps.api.main:app --port 8000
# 4. UI
cd apps/demo-web && npm install && npm run dev
```

`/health/ready` reports the index source, article/chunk counts, newest
article, the generator id and `"retrieval": "trigram-fts5"`. Keep the
archive fresh without a restart:

```sh
uv run --env-file .env python scripts/sync_index.py --index data/index/full.sqlite
```

## Evaluation

```sh
# retrieval only (fixtures + mini dataset; seconds)
uv run python evals/run_retrieval.py --verbose
# full index: headline -> own article sanity floor + latency
uv run python evals/run_retrieval.py --index data/index/full.sqlite --self-retrieval 100
# gold set: sample 100 articles for a Kinyarwanda speaker to write questions
uv run --env-file .env python scripts/make_gold_set.py --index data/index/full.sqlite --n 100 \
  --out evals/datasets/gold-v1.template.jsonl --draft-questions
# end to end with the configured generator (citations, drift, latency)
uv run --env-file .env python evals/run_answers.py --index data/index/full.sqlite \
  --dataset evals/datasets/gold-v1.jsonl --limit 30 --out /tmp/answers.jsonl
```

Measure retrieval recall separately from answer quality: almost every bad
answer is a retrieval miss wearing a generation costume.

## Layout

- `src/igihe_assistant/index/` — schema + streaming builder for the SQLite index.
- `src/igihe_assistant/retrieval/` — `store.py` (FTS5 BM25, filters in SQL),
  `query.py` (question -> trigram MATCH, stems, KI/EN lexicon, recency cues),
  `rank.py` (tiers, coverage, recency, dedupe), `rerank.py` (flag-gated).
- `src/igihe_assistant/generation/` — `Generator` protocol (`stream`/`generate`
  over chat messages), MLX/OpenAI/Ollama/fake adapters, async bridge, factory.
- `src/igihe_assistant/prompting/builder.py` — Kinyarwanda system prompt,
  few-shots, history, evidence block; `ECHO_PHRASES` for the validator.
- `apps/api/` — FastAPI (`/v1/chat` SSE: retrieval, token*, replace?, sources,
  suggestions?, done), health, sources, feedback.
- `apps/demo-web/` — Next.js chat UI (history, time filter, `replace` handling).
- `scripts/` — `build_index.py`, `sync_index.py`, `mlx_smoke.py`,
  `make_gold_set.py`, `ingest_live.py`.
- `evals/` — `run_retrieval.py`, `run_answers.py`, datasets.
- `docs/decision-log.md` — D1-D10 and deferred production gates.

Reference spec: `KINYARWANDA_CHATBOT_PLAN.md`.
