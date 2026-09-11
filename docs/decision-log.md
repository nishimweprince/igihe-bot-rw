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
