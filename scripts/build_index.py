"""Build the persistent SQLite trigram index from fetched WordPress pages.

Example:
    uv run python scripts/build_index.py --pages data/full/pages --out data/index/full.sqlite
    uv run python scripts/build_index.py --pages data/full/pages \\
        --out data/index/dev.sqlite --limit 5000

Writes to `<out>.tmp` and renames on success, so a crash never leaves a
half-built file where the API expects a good one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from igihe_assistant.index.builder import (  # noqa: E402
    bulk_build,
    iter_posts,
    load_categories,
)
from igihe_assistant.retrieval.store import IndexStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--pages", required=True, help="directory of page-*.json files")
    ap.add_argument("--out", required=True, help="index file to write")
    ap.add_argument("--limit", type=int, default=None, help="stop after N posts (dev)")
    ap.add_argument("--categories", default=None, help="optional WP categories JSON")
    ap.add_argument("--force", action="store_true", help="overwrite an existing index")
    ap.add_argument("--cache-mb", type=int, default=512)
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists() and not args.force:
        print(f"refusing to overwrite {out} (use --force)", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    for stale in (tmp, tmp.with_name(tmp.name + "-wal"), tmp.with_name(tmp.name + "-shm")):
        if stale.exists():
            stale.unlink()

    t0 = time.perf_counter()
    last = {"t": t0}

    def progress(stats):
        now = time.perf_counter()
        if now - last["t"] >= 5:
            last["t"] = now
            rate = stats.posts / max(now - t0, 1e-9)
            print(
                f"  posts={stats.posts} chunks={stats.chunks} quarantined={stats.quarantined} "
                f"{rate:.0f} posts/s",
                flush=True,
            )

    store = IndexStore.create(str(tmp), cache_mb=args.cache_mb)
    print(f"building {tmp} from {args.pages} ...", flush=True)
    stats = bulk_build(store, iter_posts(Path(args.pages), args.limit), progress=progress)
    if args.categories:
        n = load_categories(store, Path(args.categories))
        stats.extra["categories"] = n
    store.close()
    for suffix in ("-wal", "-shm"):
        side = tmp.with_name(tmp.name + suffix)
        if side.exists():
            side.unlink()
    if out.exists():
        out.unlink()
    os.replace(tmp, out)
    stats.seconds = time.perf_counter() - t0
    report = stats.as_dict() | {
        "out": str(out),
        "size_mb": round(out.stat().st_size / 1e6, 1),
        "seconds": round(stats.seconds, 1),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
