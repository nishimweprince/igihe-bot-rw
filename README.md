# IGIHE Kinyarwanda News Assistant (vertical slice)

Fixture-driven RAG slice: WordPress fixtures -> snapshots -> extraction ->
normalization -> chunking -> hybrid retrieval (FTS + fake dense, RRF) ->
grounded answer with citations and refusal. No network or model downloads
required for tests or demo.

## Quickstart (this Mac)

```sh
uv sync
uv run python scripts/ingest_fixtures.py --sample tests/fixtures/wp --out data
uv run pytest -q
uv run uvicorn apps.api.main:app --port 8000
```

Smoke (serve + chat + refusal probes):

```sh
bash scripts/smoke.sh
```

Mini eval:

```sh
uv run python evals/run_mini.py --dataset evals/datasets/mini-v1.jsonl
```

## Demo (this laptop)

```sh
# Terminal 1 — API (config comes from .env; plain `uv run` won't load it)
uv run --env-file .env uvicorn apps.api.main:app --port 8000
# Terminal 2 — chat UI
cd apps/demo-web && npm install && npm run dev
```

Open `http://localhost:3000` in a browser. For the real-model demo,
pull `ollama pull llama3.2:3b` and set `OLLAMA_MODEL=llama3.2:3b` for
terminal 1 — or point `MLX_MODEL_PATH` at a converted local checkpoint
(e.g. `models/alta-sft-v1.0-mlx`), which takes precedence and needs no
server. `NEXT_PUBLIC_API_URL` overrides the API origin for the UI.

## Layout

- `src/igihe_assistant/` — config, ingestion, extraction, normalization,
  chunking, embeddings, retrieval, prompting, generation, observability.
- `apps/api/` — FastAPI contract (`/v1/chat` SSE, health, sources, feedback).
- `migrations/` — production PostgreSQL schema (parity; not required for tests).
- `tests/fixtures/wp/` — 9 approved WordPress payload shapes.
- `evals/` — versioned mini dataset + runner (baseline numbers, not a gate).
- `docs/decision-log.md` — D1-D6 plus deferred production gates.

Reference spec: `KINYARWANDA_CHATBOT_PLAN.md`. Production decisions from its
section 23 are deferred (see decision log) and do not block this slice.
