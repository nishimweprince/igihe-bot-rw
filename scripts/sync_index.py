"""Incremental re-sync: pull posts modified since the index's newest `modified`.

    uv run python scripts/sync_index.py --index data/index/full.sqlite [--since 2026-08-01T00:00:00]

Pages `orderby=modified&order=desc` with `modified_after=<since>`, stops as
soon as a page's oldest `modified` falls before `since` (so it also works if
the WordPress build ignores `modified_after`), keeps the raw page JSON under
`<pages>/sync-<ts>-<n>.json`, and upserts into the live index (WAL: the API
keeps serving reads while this writes).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ingest_live import HttpxTransport  # noqa: E402

from igihe_assistant.config import Settings  # noqa: E402
from igihe_assistant.index.builder import upsert_posts  # noqa: E402
from igihe_assistant.ingestion.wordpress import WordPressClient  # noqa: E402
from igihe_assistant.retrieval.store import IndexStore  # noqa: E402


def fetch_modified_since(client, since: str, per_page: int, pages_dir: Path | None,
                         gap: float = 1.0, max_pages: int = 500) -> list[dict]:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    out: list[dict] = []
    for page in range(1, max_pages + 1):
        items, _headers = client.fetch_posts(
            page, per_page, orderby="modified", order="desc", modified_after=since
        )
        if not items:
            break
        if pages_dir is not None:
            pages_dir.mkdir(parents=True, exist_ok=True)
            (pages_dir / f"sync-{stamp}-{page}.json").write_text(
                json.dumps(items, ensure_ascii=False), encoding="utf-8"
            )
        fresh = [p for p in items if str(p.get("modified") or "") > since]
        out.extend(fresh)
        if len(fresh) < len(items) or len(items) < per_page:
            break
        time.sleep(gap)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", required=True)
    ap.add_argument("--since", default=None, help="ISO timestamp; default: index meta")
    ap.add_argument("--pages", default="data/full/pages", help="where to keep raw page JSON")
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--base-url", default=None)
    args = ap.parse_args()

    settings = Settings()
    store = IndexStore(args.index, read_only=False)
    since = args.since or store.meta().get("max_modified_at") or store.stats()["max_modified_at"]
    if not since:
        print("index has no modified_at; build it first", file=sys.stderr)
        return 2
    client = WordPressClient(
        base_url=args.base_url or settings.wordpress_base_url,
        transport=HttpxTransport("igihe-assistant/0.2 (+sync)"),
    )
    print(f"syncing posts modified after {since} from {client.base_url} ...", flush=True)
    posts = fetch_modified_since(client, since, args.per_page, Path(args.pages))
    stats = upsert_posts(store, posts)
    store.close()
    print(json.dumps({"since": since, "fetched": len(posts), **stats.as_dict()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
