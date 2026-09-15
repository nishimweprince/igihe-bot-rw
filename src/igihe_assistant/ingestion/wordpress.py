"""WordPress REST client with injectable transport (fixture-friendly)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

ALLOWED_FIELDS = (
    "id,slug,status,date,modified,link,title,excerpt,content,author,categories,tags,featured_media"
)


class Transport(Protocol):
    def get(self, url: str, params: dict[str, Any]) -> Any: ...


@dataclass
class WordPressClient:
    base_url: str
    transport: Transport
    user_agent: str = "igihe-assistant/0.1 (+ops@igihe.example)"
    max_retries: int = 4

    def fetch_posts(
        self,
        page: int,
        per_page: int = 100,
        orderby: str = "date",
        order: str = "asc",
        *,
        after: str | None = None,
        before: str | None = None,
        modified_after: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        params: dict[str, Any] = {
            "_fields": ALLOWED_FIELDS,
            "per_page": per_page,
            "page": page,
            "orderby": orderby,
            "order": order,
        }
        # Date windows beat deep `page=N` offsets on a 200k-post archive.
        for key, value in (
            ("after", after),
            ("before", before),
            ("modified_after", modified_after),
        ):
            if value:
                params[key] = value
        url = self.base_url.rstrip("/") + "/wp-json/wp/v2/posts"
        delay = 0.2
        last_exc: Exception | None = None
        for _ in range(self.max_retries):
            try:
                resp = self.transport.get(url, params)
                return resp.items, resp.headers
            except RetryableError as exc:
                last_exc = exc
                retry_after = getattr(exc, "retry_after", None)
                time.sleep(retry_after if retry_after else delay)
                delay = min(delay * 2, 5.0)
        raise RuntimeError(f"wordpress fetch failed after retries: {last_exc}")


class _Retryable(Exception):
    def __init__(self, msg: str = "retryable", retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


# Public alias for transports (e.g. live HTTP) signalling a retryable failure.
RetryableError = _Retryable
