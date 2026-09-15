# Demo runbook (laptop, 8 GB RAM)

Audience: IGIHE staff demo. Everything runs from this repo; the corpus,
index, models, conversations and secrets are gitignored.

## 1. One-time preparation

```sh
uv sync --extra dev --extra mlx
# archive already fetched under data/full/pages (202,756 posts)
uv run python scripts/build_index.py --pages data/full/pages --out data/index/full.sqlite
uv run python scripts/mlx_smoke.py        # expect a cited Kinyarwanda answer, ~1-2 s warm
```

## 2. Start order (2 terminals)

```sh
# Terminal 1 — API (config comes from .env; plain `uv run` won't load it)
uv run --env-file .env uvicorn apps.api.main:app --port 8000
# wait for "generator.warm" in the log (~15-30 s: weights + Metal warm-up)

# Terminal 2 — chat UI
cd apps/demo-web && npm install && npm run dev
```

Open `http://localhost:3000`. Health: `GET http://localhost:8000/health/ready`
reports `"articles": 198633`, `"model": "mlx:gemma-4-e2b-it-mlx"`,
`"retrieval": "trigram-fts5"`.

## 3. Guided demo script

1. Factual: `Perezida Kagame yavuze iki ku Rwanda na RDC?` — short cited
   answer, tokens appear as they are generated, sources open the article.
2. Latest: `Mbwira inkuru ziheruka` — browse mode, newest stories, cited.
3. Code-switched: `football results this week` — English words map to
   `umupira w'amaguru`, recent matches only.
4. Follow-up: after (1), ask `None se muri Congo?` — the previous question's
   terms travel with the follow-up.
5. Time filter: pick `Iminsi 7` under the composer and ask again.
6. Refusal: `Ninde watwaye igikombe cy'isi cya 2030?` — no evidence, exact
   refusal, near matches shown as such, sendable suggestion chips.

## 4. Measured (this laptop, 2026-09-15)

- Index: 198,633 articles / 219,152 chunks, 3.1 GB, built in 5 m 20 s.
- Retrieval: p50 ~750 ms on headline-length queries, 300-600 ms on typical
  questions; self-retrieval recall@1 0.93 / recall@10 0.95 (n=100).
- Generation (Gemma 4 E2B 4-bit, warm): TTFT ~1.3 s, 45-55 tok/s, peak 3.2 GB.
- Fixture retrieval eval: recall@10 1.0, refusal 1.0 (`evals/run_retrieval.py`).

## 5. Known limits (say these out loud)

- E2B is a small model: it can misread a number or drop a citation. The
  validator replaces uncited/echoed output with the refusal (`event:
  replace`) — a refusal on a good question is the guard, not a crash.
  `VALIDATION_RETRY=true` buys one buffered second attempt.
- Retrieval is lexical: paraphrases with no shared substring miss. The
  KI/EN lexicon and prefix stems cover the common cases; the gold set
  will show the rest.
- One generation at a time (MLX). Concurrent users see "Serivisi iruzuye".

## 6. Troubleshooting

- `"model": "fake-gen-v1"` → `GENERATOR`/`MLX_MODEL_PATH` unset or the
  model dir missing (startup log `generator.config_fallback`).
- `"index": "fixtures"` → `INDEX_PATH` unset or file missing.
- Slow first answer → warm-up did not run (`WARMUP=false`) or the machine
  is swapping (close browsers; the model needs ~3.5 GB free).
- Port clashes → API `--port 8001` + `NEXT_PUBLIC_API_URL` for the UI.
