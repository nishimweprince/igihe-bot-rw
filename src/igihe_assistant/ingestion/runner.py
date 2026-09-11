"""Idempotent fixture ingestion: snapshots, audit rows, quarantine."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .snapshots import sha256_of, write_snapshot


@dataclass
class IngestionResult:
    run_id: str
    fetched: int = 0
    changed: int = 0
    unchanged: int = 0
    failed: int = 0
    failures: list[dict] = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


def _modified_epoch(post: dict) -> int:
    raw = post.get("modified") or post.get("date") or ""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int(dt.timestamp())
    except ValueError:
        return 0


def ingest_posts(
    posts: list[dict],
    out: Path,
    code_version: str = "0.1.0",
    extraction_version: str = "extract-v1",
) -> IngestionResult:
    run_id = str(uuid.uuid4())
    started = time.time()
    raw_root = out / "raw"
    result = IngestionResult(run_id=run_id)
    seen: dict[int, str] = {}
    for post in posts:
        result.fetched += 1
        try:
            wp_id = int(post["id"])
        except (KeyError, TypeError, ValueError):
            result.failed += 1
            result.failures.append({"reason": "missing-id", "post": str(post)[:200]})
            continue
        if wp_id in seen:
            continue
        digest = sha256_of(post)
        seen[wp_id] = digest
        epoch = _modified_epoch(post)
        path, _ = write_snapshot(raw_root, post, epoch)
        rel = str(path.relative_to(out))
        prev = result.manifest.get(str(wp_id))
        if prev and prev["sha256"] == digest:
            result.unchanged += 1
        else:
            result.changed += 1
        result.manifest[str(wp_id)] = {
            "sha256": digest,
            "raw_key": rel,
            "modified": post.get("modified"),
        }
    run_record = {
        "run_id": run_id,
        "code_version": code_version,
        "extraction_version": extraction_version,
        "fetched": result.fetched,
        "changed": result.changed,
        "unchanged": result.unchanged,
        "failed": result.failed,
        "failures": result.failures,
        "duration_s": round(time.time() - started, 3),
    }
    manifests = out / "raw" / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / f"{run_id}.json").write_text(json.dumps(run_record, indent=2), encoding="utf-8")
    (out / "manifest.json").write_text(
        json.dumps(result.manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    return result
