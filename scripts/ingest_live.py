"""Live sample ingestion from old.igihe.com (polite, resumable, gitignored).

Example:
    uv run python scripts/ingest_live.py --pages 3 --per-page 100 --out data/live-sample
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx  # noqa: E402

from igihe_assistant.extraction.parser import extract, rendered_text  # noqa: E402
from igihe_assistant.ingestion.runner import ingest_posts  # noqa: E402
from igihe_assistant.ingestion.wordpress import RetryableError, WordPressClient  # noqa: E402
from igihe_assistant.pipeline import build_index  # noqa: E402


@dataclass
class HttpxResponse:
    items: list
    headers: dict


class HttpxTransport:
    def __init__(self, user_agent: str):
        self._client = httpx.Client(
            timeout=30, headers={"User-Agent": user_agent}, follow_redirects=True
        )

    def get(self, url: str, params: dict) -> HttpxResponse:
        try:
            resp = self._client.get(url, params=params)
        except httpx.TransportError as exc:
            raise RetryableError(f"transport: {exc}") from exc
        if resp.status_code in (429, 500, 502, 503, 504):
            retry_after = resp.headers.get("Retry-After")
            raise RetryableError(
                f"http {resp.status_code}",
                float(retry_after) if retry_after and retry_after.isdigit() else None,
            )
        resp.raise_for_status()
        return HttpxResponse(resp.json(), dict(resp.headers))


def fetch_pages(client, per_page, start_page, pages, pages_dir, gap=1.0):
    """Fetch listing pages to disk. `pages=0` keeps going until a short page.

    Returns (posts, wp_total). File per page makes reruns resumable via
    --start-page; the polite gap applies between requests.
    """
    posts: list[dict] = []
    wp_total: str | None = None
    page = start_page
    fetched = 0
    while True:
        if pages > 0 and fetched >= pages:
            break
        items, headers = client.fetch_posts(page, per_page, "date", "desc")
        lowered = {k.lower(): v for k, v in headers.items()}
        wp_total = lowered.get("x-wp-total", wp_total)
        (pages_dir / f"page-{page}.json").write_text(
            json.dumps(items, ensure_ascii=False), encoding="utf-8"
        )
        posts.extend(items)
        fetched += 1
        print(f"page {page}: {len(items)} posts (wp-total={wp_total})", flush=True)
        if pages == 0 and len(items) < per_page:
            break
        page += 1
        time.sleep(gap)
    return posts, wp_total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--pages",
        type=int,
        default=3,
        help="Pages to fetch; 0 = all, stopping at the first short page.",
    )
    ap.add_argument(
        "--start-page",
        type=int,
        default=1,
        help="First page to fetch (resume a long run without refetching).",
    )
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--out", default="data/live-sample")
    ap.add_argument("--base-url", default="https://old.igihe.com")
    ap.add_argument(
        "--user-agent",
        default=WordPressClient.user_agent,
        help="HTTP User-Agent (some hosts block the default bot UA)",
    )
    args = ap.parse_args()

    out = Path(args.out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    client = WordPressClient(args.base_url, HttpxTransport(args.user_agent))
    posts, wp_total = fetch_pages(
        client, args.per_page, args.start_page, args.pages, out / "pages"
    )

    result = ingest_posts(posts, out)
    ok = quarantined = 0
    for post in posts:
        if extract(rendered_text(post))["status"] == "ok":
            ok += 1
        else:
            quarantined += 1
    backend, by_id, articles = build_index(posts)
    report = {
        "run_id": result.run_id,
        "wp_total": wp_total,
        "fetched": result.fetched,
        "changed": result.changed,
        "failed": result.failed,
        "extract_ok": ok,
        "quarantined": quarantined,
        "articles_indexed": len(articles),
        "chunks_indexed": len(by_id),
    }
    (out / "index_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
