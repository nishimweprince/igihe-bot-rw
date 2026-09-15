#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen --extra dev
uv run python scripts/ingest_fixtures.py --sample tests/fixtures/wp --out data || true
uv run pytest -q
uv run uvicorn apps.api.main:app --port 8000 &
SRV=$!
trap "kill $SRV" EXIT
sleep 4
curl -sf localhost:8000/health/live
curl -sf localhost:8000/health/ready
curl -sN -X POST localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke","message":"Amazi meza i Kigali?"}' | head -n 12
curl -sN -X POST localhost:8000/v1/chat -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke","message":"Ni iki cyabaye ku mubumbe Mars?"}' | tail -n 6
echo SMOKE_OK
