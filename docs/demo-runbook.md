# Demo-day runbook (laptop, 8 GB RAM)

Audience: IGIHE staff demo. Everything runs from this repo; no corpus,
snapshots, conversations, or secrets are committed (`data/` is gitignored).

## 1. Start order (3 terminals)

```sh
# Terminal 1 — model (one-time): ollama pull llama3.2:3b
ollama serve  # skip if the Ollama app is already running

# Terminal 2 — API on the live sample + real model (config comes from .env)
uv run --env-file .env uvicorn apps.api.main:app --port 8000

# Terminal 3 — chat UI
cd apps/demo-web && npm install && npm run dev
```

Open `http://localhost:3000` in a browser. Health: `GET
http://localhost:8000/health/ready` should report `"articles": 293`
and `"ollama_model": "llama3.2:3b"`.

Demo tuning (measured on this laptop, 2026-09-11): 3 evidence sources ×
500 chars, lexical-candidate retrieval, one citation-nudge retry, and a
validator that replaces echo/citation-less output with the approved
refusal. Defaults in `.env.example` stay reference-faithful
(hybrid RRF, 6 sources); the flags above are the demo profile.

## 2. Guided demo script (verified live)

1. Factual, in-sample: `Abahinga bacibwa amande?` → short cited
   answer `Abahinga bazacibwa amande [1].` plus a clickable source
   (article 253425). This is the "it works" moment.
2. Refusal: `Ni iki cyabaye ku mubumbe Mars ejo?` → approved
   no-evidence wording, empty sources. Makes the trust point: no
   archive support, no answer.
3. Show a source link opening the original article.

## 3. Measured baselines (laptop, 2026-09-11)

- Live sample: 300 fetched, 293 indexed, 7 quarantined, 331 chunks;
  archive header `x-wp-total: 202756`.
- Fixture mini-eval: Recall@5 1.0, Recall@10 1.0, MRR 0.905,
  citation resolution 1.0, refusal 1.0.
- Live-sample probe with the real 3B model (`scripts/probe_live.py`):
  self-Recall@5 0.85, self-Recall@10 0.9, self-MRR 0.635,
  citation resolution 0.0 on title-fragment queries (outputs refused
  rather than hallucinated — safe direction), refusal accuracy 1.0
  on off-corpus questions. Baseline only, not a gate.
- Real-model latency (`scripts/latency_probe.py`, 120 output tokens):
  concurrency 1 → median total 1.8 s; 2 → 2.2 s (max 3.9 s);
  4 → 2.3 s (max 4.5 s). First-token equals total: the server
  generates fully, then streams (streaming passthrough is follow-up work).

## 4. Sizing note (10k chats/day)

10,000 msgs/day ≈ 0.12 msgs/s average. Peaks, not averages, matter:
each 3B generation occupies the model worker for seconds, so sustained
bursts above ~4 concurrent chats queue (bounded semaphore + localized
busy message). If the pilot expects hotter peaks: shorter answers,
stricter admission control, or a GPU host — that decision is the
production capacity gate, not this demo.

## 5. Known demo limits (say these out loud)

- The 3B model is flaky: it sometimes echoes prompt text or drops
  citations. The validator catches all observed shapes (unknown
  citations, unindexed URLs, evidence/instruction echo, missing
  citations, one retry) and replaces them with refusal — nothing
  uncited streams as authoritative. Some good questions therefore
  refuse; that is the guard working, not a crash.
- Dense vectors are deterministic placeholders (`fake-hash-v1`); the
  demo retrieval mode requires lexical support
  (`RETRIEVAL_CANDIDATES=lexical`). Real multilingual embeddings are
  the top follow-up (needs the editor-reviewed bake-off first).
- Token streaming is buffered server-side; time-to-first-token equals
  total time today.

## 6. Troubleshooting

- `ollama_model: fake-gen-v1` in `/health/ready` → `OLLAMA_MODEL`
  was unset when the API started; restart terminal 2 with it set.
- Empty answers on every question → check `SAMPLE_DIR` points at
  `data/live-sample/pages`; without it the API serves the 9 fixtures.
- Port clashes → API `--port 8001` + `NEXT_PUBLIC_API_URL` for the UI.
- Kill demo servers: `Ctrl-C` each terminal; nothing persists except
  gitignored `data/`.
