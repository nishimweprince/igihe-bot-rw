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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--per-page", type=int, default=100)
    ap.add_argument("--out", default="data/live-sample")
    ap.add_argument("--base-url", default="https://old.igihe.com")
    args = ap.parse_args()

    out = Path(args.out)
    (out / "pages").mkdir(parents=True, exist_ok=True)
    client = WordPressClient(args.base_url, HttpxTransport(WordPressClient.user_agent))
    posts: list[dict] = []
    wp_total: str | None = None
    for page in range(1, args.pages + 1):
        items, headers = client.fetch_posts(page, args.per_page, "date", "desc")
        lowered = {k.lower(): v for k, v in headers.items()}
        wp_total = lowered.get("x-wp-total", wp_total)
        (out / "pages" / f"page-{page}.json").write_text(
            json.dumps(items, ensure_ascii=False), encoding="utf-8"
        )
        posts.extend(items)
        print(f"page {page}: {len(items)} posts (wp-total={wp_total})", flush=True)
        time.sleep(1.0)  # polite gap between pages

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
