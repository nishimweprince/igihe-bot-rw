"""Full-archive pagination: until-exhausted and resume, offline via a stub client."""

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ingest_live.py"


def _load():
    sys.path.insert(0, str(SCRIPT.parents[1] / "src"))
    spec = importlib.util.spec_from_file_location("ingest_live", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ingest_live"] = mod
    spec.loader.exec_module(mod)
    return mod


class StubClient:
    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def fetch_posts(self, page, per_page, *args):
        self.calls.append(page)
        return self._pages.get(page, []), {"X-WP-Total": "250"}


def _posts(n, start=1):
    return [{"id": i} for i in range(start, start + n)]


def test_pages_zero_stops_at_first_short_page(tmp_path):
    mod = _load()
    client = StubClient({1: _posts(100), 2: _posts(100, 101), 3: _posts(30, 201)})
    posts, total = mod.fetch_pages(client, 100, 1, 0, tmp_path, gap=0)
    assert client.calls == [1, 2, 3]
    assert len(posts) == 230
    assert total == "250"
    assert json.loads((tmp_path / "page-3.json").read_text()) == _posts(30, 201)


def test_fixed_pages_unchanged(tmp_path):
    mod = _load()
    client = StubClient({1: _posts(100), 2: _posts(100, 101), 3: _posts(100, 201)})
    posts, _ = mod.fetch_pages(client, 100, 1, 2, tmp_path, gap=0)
    assert client.calls == [1, 2]
    assert len(posts) == 200


def test_start_page_resumes_without_refetching(tmp_path):
    mod = _load()
    client = StubClient({2: _posts(100, 101), 3: _posts(100, 201)})
    posts, _ = mod.fetch_pages(client, 100, 2, 2, tmp_path, gap=0)
    assert client.calls == [2, 3]
    assert len(posts) == 200
    assert (tmp_path / "page-2.json").exists()
    assert not (tmp_path / "page-1.json").exists()


def test_fetch_posts_only_sends_window_params_when_set():
    from igihe_assistant.ingestion.wordpress import WordPressClient

    seen = []

    class T:
        def get(self, url, params):
            seen.append(params)

            class R:
                items = []
                headers = {}

            return R()

    c = WordPressClient(base_url="https://x", transport=T())
    c.fetch_posts(1)
    c.fetch_posts(2, orderby="modified", order="desc", modified_after="2026-08-01T00:00:00")
    assert "modified_after" not in seen[0] and "after" not in seen[0]
    assert seen[1]["modified_after"] == "2026-08-01T00:00:00" and seen[1]["orderby"] == "modified"
