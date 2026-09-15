# Decision log

## Slice decisions (D1-D6, locked 2026-09-11)

- D1: Build in place in `igihe-bot-rw`. Provisional reference name
  `igihe-rw-assistant` is a rename/transfer question for later, not this task.
- D2: Python 3.12 + FastAPI + Pydantic + `uv` per reference section 5.2.
- D3: Ship Postgres migrations for parity; verify by default on SQLite FTS +
  in-memory fake dense behind a `RetrievalBackend` protocol.
- D4: Fake embedder/generator behind strict adapter interfaces; real
  citation validation, token budgeting, refusal, streaming.
- D5: Hybrid RRF retrieval, no reranker (disabled interface only).
- D6: ALTA out of the request path (stub lane only).

## Phase 0 resolutions (answered 2026-09-11, demo track)

- Traffic: 100k/day = site visitors; size chatbot path for ~10k chats/day.
- Demo hardware: this laptop, 8 GB RAM, 512 GB SSD (Ubuntu rollout deferred).
- Generation: open-source Llama via Ollama; pull a small ~3B instruction
  model for the 8 GB demo (no model pulled yet at goal time).
- Reviewers: IGIHE staff, on the final demo.
- Scope: demo-ready on laptop (live few-hundred-article sample, real
  model, demo UI, measured numbers). Full bake-off, Ubuntu rollout, and
  production hardening are later tracks.

## Deferred production gates (reference plan section 23)

1. 100k/day meaning (visits vs sessions vs messages) — open.
2. Ubuntu CPU/RAM/disk + backup storage inventory — open.
3. Approved Llama variants/licenses + pinned digests — open.
4. GPU fallback availability — open.
5. Content scope (news/opinion/sponsored/announcements/video/photo) — open.
6. Second-site ingest (current Kinyarwanda site) — open.
7. Production frontend/auth conventions — open.
8. Retention policy (snapshots/logs/feedback) — open.
9. Editorial reviewers + no-evidence wording authority — open.
10. Standard platform/secret/backup/monitoring tooling — open.

## Full-corpus track (2026-09-15)

Context: the slice could not serve the fetched 200k-article archive on the
8 GB laptop (in-memory index rebuilt per process, hash-vector "dense"
retrieval, synchronous generation, prompt-string re-parsing in every
adapter). Measured on this machine while deciding:

- SQLite 3.53 in the venv has the FTS5 `trigram` tokenizer; full build
  198,633 articles / 219,152 chunks in 5 m 20 s, 3.1 GB on disk, builder
  RSS < 1 GB. Trigram FTS is disk-heavy and RAM-cheap.
- Ranking must happen inside the FTS subquery before joining `chunks`:
  joining first cost 2.4 s for "kagame" (18k matches), 35 ms after.
  Headline-length queries (6-10 terms): p50 750 ms, p95 1.6 s; typical
  2-4-term questions 300-600 ms. Self-retrieval floor (headline -> own
  article, n=100): recall@1 0.93, recall@10 0.95, MRR 0.94.
- Gemma 4 E2B 4-bit via mlx-lm 0.31.3: loads (13 s), warm prefill
  ~1,800 tok/s, decode 45-55 tok/s, peak 3.2 GB; ~1.5-2 s per cited answer
  on a ~1.1k-token prompt. First call pays 15-30 s of Metal JIT, hence
  `WARMUP=true`. The model spontaneously opens a `<|channel>thought` block
  (English reasoning) unless that token is banned at the logits; prefilling
  an empty thought block made it reason in plain text instead. Few-shots
  matter: without them the answer format collapses.

- D7 (supersedes D3): one SQLite file is the index — `articles`, `chunks`,
  `chunks_fts` (external content, trigram, `remove_diacritics 1`), `meta`.
  Opened read-only for serving; `scripts/sync_index.py` upserts through WAL
  using WP `modified_after`. Postgres/pgvector migration deleted.
- D8 (supersedes D5): retrieval is lexical-only trigram BM25 (title x3) with
  strict-AND then loose-OR tiers of per-term groups (full form | class-prefix
  stem | KI<->EN lexicon), score x (0.5 + 0.5 coverage) x recency decay
  anchored to the newest article (weight 0.3 / half-life 365 d; with a
  recency cue 1.0 / 30 d plus a 180-day hard window that falls back when it
  yields < 3 hits). Questions with no topic term ("Mbwira inkuru ziheruka")
  take browse mode: newest-first round-up. The refusal gate is evidence-set
  coverage >= MIN_COVERAGE (0.5), not "any lexical hit". No dense vectors;
  a reranker stays behind `RERANKER_MODEL` until a gold-set bake-off shows
  >= +5 recall@10 (memory next to the MLX model is the constraint).
- D9 (supersedes D6 and the Phase-0 "Llama via Ollama"): Gemma 4 E2B on MLX
  is the request-path generator; `GENERATOR=fake|mlx|openai|ollama` is
  explicit (a set OpenAI key alone selects nothing). `Generator.stream/
  generate(system, messages, max_tokens)`; adapters no longer re-parse a
  flat prompt. ALTA checkpoints and converter retired.
- D10: real token streaming (worker thread -> asyncio queue). Validation
  runs incrementally on the accumulated text (echo, unknown citation) and
  fully at the end (URLs, no-citation); a failure emits `event: replace`
  with the refusal (or a buffered retry when `VALIDATION_RETRY=true`) and
  the retrieved stories become disclaimed near matches. Frontend concatenates
  tokens verbatim and handles `replace`.
- D11: prompt = Kinyarwanda system turn (own words, 1-3 sentences, `[n]`,
  no URLs, exact refusal string) + 3 few-shot pairs on fictional stories +
  last 6 conversation turns + evidence block without URLs/ids. One-term
  follow-ups borrow the previous question's terms before retrieval.

Open after this track: gold-v1 questions (100, human-written; the template
tooling exists), the answer-quality baseline from `evals/run_answers.py`,
`MIN_COVERAGE`/recency tuning on that set, IGIHE English-edition ingest for
cross-lingual recall, and the reranker bake-off.
