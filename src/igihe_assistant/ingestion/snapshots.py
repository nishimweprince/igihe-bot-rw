"""Immutable gzip raw snapshots + sha256 manifests."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC
from pathlib import Path


def canonical_fields(post: dict) -> dict:
    return {
        k: post.get(k)
        for k in (
            "id",
            "slug",
            "status",
            "date",
            "modified",
            "link",
            "title",
            "excerpt",
            "content",
            "author",
            "categories",
            "tags",
            "featured_media",
        )
    }


def sha256_of(post: dict) -> str:
    blob = json.dumps(canonical_fields(post), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def snapshot_path(root: Path, wp_id: int, modified_epoch: int) -> Path:
    from datetime import datetime

    dt = datetime.fromtimestamp(modified_epoch, tz=UTC)
    return (
        root
        / "posts"
        / f"{dt.year:04d}"
        / f"{dt.month:02d}"
        / str(wp_id)
        / f"{modified_epoch}.json.gz"
    )


def write_snapshot(root: Path, post: dict, modified_epoch: int) -> tuple[Path, str]:
    digest = sha256_of(post)
    path = snapshot_path(root, int(post["id"]), modified_epoch)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path, digest
    blob = json.dumps(post, ensure_ascii=False).encode("utf-8")
    with gzip.open(path, "wb") as fh:
        fh.write(blob)
    return path, digest
