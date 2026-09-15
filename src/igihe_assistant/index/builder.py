"""Streaming builder: WordPress post JSON -> articles + chunks + FTS rows.

Never holds the corpus in memory: pages are read one file at a time and
written in batches. `bulk_build` is the fast first build (triggers off, FTS
rebuilt once); `upsert_posts` is the trigger-backed path used by incremental
sync and by tests.
"""

from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..chunking.chunker import CHUNK_VERSION, chunk_article
from ..extraction.parser import extract, rendered_text, rendered_title
from ..ingestion.snapshots import sha256_of
from ..normalization.normalize import normalize_original
from ..retrieval.store import IndexStore
from .schema import DROP_TRIGGERS_SQL, SCHEMA_VERSION, TRIGGERS_SQL

EXTRACTION_VERSION = "extract-v1"
_EPOCH = date(1970, 1, 1)
_PAGE_NUM = re.compile(r"(\d+)")


def published_day(iso: str) -> int:
    """Days since epoch for a WP ISO timestamp; 0 when unparseable."""
    try:
        return (datetime.fromisoformat(iso[:19]).date() - _EPOCH).days
    except (ValueError, TypeError):
        return 0


@dataclass
class PreparedPost:
    article: dict
    chunks: list[dict]


@dataclass
class BuildStats:
    posts: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0
    quarantined: int = 0
    chunks: int = 0
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "extra"} | self.extra


def prepare_post(post: dict) -> PreparedPost | None:
    """Parse/normalise/chunk one post. `None` when the post has no id."""
    try:
        wp_id = int(post["id"])
    except (KeyError, TypeError, ValueError):
        return None
    title = normalize_original(html.unescape(rendered_title(post)))
    pub = str(post.get("date") or "")
    cats = [int(c) for c in (post.get("categories") or []) if str(c).lstrip("-").isdigit()]
    category_id = cats[0] if cats else None
    article = {
        "wp_id": wp_id,
        "title": title,
        "url": str(post.get("link") or ""),
        "published_at": pub,
        "published_day": published_day(pub),
        "modified_at": str(post.get("modified") or pub),
        "category_id": category_id,
        "category_ids": json.dumps(cats),
        "status": "ok",
        "sha256": sha256_of(post),
        "body": None,
    }
    parsed = extract(rendered_text(post))
    if parsed["status"] != "ok":
        article["status"] = "quarantined"
        return PreparedPost(article, [])
    article["body"] = normalize_original("\n".join(t for _, t in parsed["blocks"]))
    chunks = []
    for ch in chunk_article(
        wp_id, title, str(category_id or ""), pub, parsed["blocks"], EXTRACTION_VERSION
    ):
        chunks.append(
            {
                "chunk_uid": ch["id"],
                "wp_id": wp_id,
                "chunk_index": ch["chunk_index"],
                "title": title,
                "heading": ch.get("heading") or "",
                "content": ch["content"],
                "published_at": pub,
                "published_day": article["published_day"],
                "category_id": category_id,
            }
        )
    return PreparedPost(article, chunks)


# -- input ---------------------------------------------------------------------


def iter_page_files(pages_dir: Path) -> list[Path]:
    """`page-N.json` in numeric order, then any `sync-*.json` by name."""
    pages = sorted(
        pages_dir.glob("page-*.json"),
        key=lambda p: int(_PAGE_NUM.search(p.stem).group(1)) if _PAGE_NUM.search(p.stem) else 0,
    )
    return pages + sorted(pages_dir.glob("sync-*.json"))


def iter_posts(pages_dir: Path, limit: int | None = None) -> Iterator[dict]:
    """Yield posts one page file at a time (~400 KB each), never the corpus."""
    n = 0
    for path in iter_page_files(Path(pages_dir)):
        posts = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(posts, dict):
            posts = [posts]
        for post in posts:
            yield post
            n += 1
            if limit is not None and n >= limit:
                return


# -- write ---------------------------------------------------------------------

_ARTICLE_COLS = (
    "wp_id, title, url, published_at, published_day, modified_at, category_id, "
    "category_ids, status, sha256, body"
)
_CHUNK_COLS = (
    "chunk_uid, wp_id, chunk_index, title, heading, content, published_at, "
    "published_day, category_id"
)


def _write_one(conn, prepared: PreparedPost, stats: BuildStats) -> None:
    art = prepared.article
    row = conn.execute(
        "SELECT modified_at, sha256 FROM articles WHERE wp_id = ?", (art["wp_id"],)
    ).fetchone()
    if row is not None:
        if row["sha256"] == art["sha256"] or row["modified_at"] > art["modified_at"]:
            stats.skipped += 1
            return
        conn.execute("DELETE FROM chunks WHERE wp_id = ?", (art["wp_id"],))
        stats.updated += 1
    else:
        stats.inserted += 1
    conn.execute(
        f"INSERT OR REPLACE INTO articles({_ARTICLE_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [art[c] for c in _ARTICLE_COLS.replace(" ", "").split(",")],
    )
    if art["status"] != "ok":
        stats.quarantined += 1
        return
    conn.executemany(
        f"INSERT INTO chunks({_CHUNK_COLS}) VALUES (?,?,?,?,?,?,?,?,?)",
        [[ch[c] for c in _CHUNK_COLS.replace(" ", "").split(",")] for ch in prepared.chunks],
    )
    stats.chunks += len(prepared.chunks)


def delete_article(conn, wp_id: int) -> bool:
    cur = conn.execute("DELETE FROM chunks WHERE wp_id = ?", (int(wp_id),))
    cur = conn.execute("DELETE FROM articles WHERE wp_id = ?", (int(wp_id),))
    return cur.rowcount > 0


def write_posts(
    store: IndexStore,
    posts: Iterable[dict],
    batch: int = 500,
    progress: Callable[[BuildStats], None] | None = None,
) -> BuildStats:
    """Upsert posts in batches; unpublished posts are removed."""
    t0 = time.perf_counter()
    stats = BuildStats()
    conn = store.conn
    n_in_batch = 0
    for post in posts:
        stats.posts += 1
        status = str(post.get("status") or "publish")
        if status != "publish":
            try:
                if delete_article(conn, int(post["id"])):
                    stats.deleted += 1
            except (KeyError, TypeError, ValueError):
                pass
        else:
            prepared = prepare_post(post)
            if prepared is not None:
                _write_one(conn, prepared, stats)
        n_in_batch += 1
        if n_in_batch >= batch:
            conn.commit()
            n_in_batch = 0
            if progress:
                stats.seconds = time.perf_counter() - t0
                progress(stats)
    conn.commit()
    stats.seconds = time.perf_counter() - t0
    return stats


def upsert_posts(
    store: IndexStore, posts: Iterable[dict], batch: int = 500, progress=None
) -> BuildStats:
    """Incremental path: triggers keep the FTS table in sync; meta refreshed."""
    stats = write_posts(store, posts, batch=batch, progress=progress)
    _write_meta(store, stats)
    return stats


def bulk_build(
    store: IndexStore, posts: Iterable[dict], batch: int = 1000, progress=None
) -> BuildStats:
    """First build: triggers off, one FTS rebuild, optimise, then WAL."""
    conn = store.conn
    on_disk = store.path != ":memory:"
    if on_disk:
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA journal_mode=OFF")
    conn.executescript(DROP_TRIGGERS_SQL)
    stats = write_posts(store, posts, batch=batch, progress=progress)
    t0 = time.perf_counter()
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('rebuild')")
    conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES ('optimize')")
    conn.executescript(TRIGGERS_SQL)
    conn.commit()
    if on_disk:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    stats.extra["fts_seconds"] = round(time.perf_counter() - t0, 1)
    stats.seconds += time.perf_counter() - t0
    _write_meta(store, stats)
    return stats


def _write_meta(store: IndexStore, stats: BuildStats) -> None:
    s = store.stats()
    store.set_meta(
        schema_version=SCHEMA_VERSION,
        extraction_version=EXTRACTION_VERSION,
        chunk_version=CHUNK_VERSION,
        tokenizer="trigram",
        built_at=datetime.now().isoformat(timespec="seconds"),
        posts=stats.posts,
        articles=s["articles"],
        chunks=s["chunks"],
        max_published_at=s["max_published_at"],
        max_modified_at=s["max_modified_at"],
    )


def load_categories(store: IndexStore, path: Path) -> int:
    """Optional: WP categories JSON (list of {id,name,slug}) -> categories."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    data = [
        (int(r["id"]), html.unescape(str(r.get("name", ""))), str(r.get("slug", "")))
        for r in rows
        if "id" in r
    ]
    store.conn.executemany(
        "INSERT OR REPLACE INTO categories(id, name, slug) VALUES (?, ?, ?)", data
    )
    store.conn.commit()
    return len(data)
