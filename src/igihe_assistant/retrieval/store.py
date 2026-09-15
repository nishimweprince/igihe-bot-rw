"""Read side of the persistent index: FTS5 trigram BM25 + row lookups.

One `IndexStore` per process. The file is opened read-only for serving so a
concurrent `scripts/sync_index.py` writer (WAL) can update it in place; the
`:memory:` form is used by tests and evals built from fixtures.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..index.schema import SCHEMA_SQL, SCHEMA_VERSION, TRIGGERS_SQL

CHUNK_COLUMNS = (
    "cid, chunk_uid, wp_id, chunk_index, title, heading, content, "
    "published_at, published_day, category_id"
)


@dataclass(frozen=True)
class Hit:
    cid: int
    bm25: float  # FTS5 bm25(): lower (more negative) is better
    wp_id: int
    published_day: int


def _filter_sql(filters: dict | None, alias: str = "c") -> tuple[str, list]:
    """Translate the public filter dict into SQL predicates + params."""
    clauses: list[str] = []
    params: list = []
    if not filters:
        return "", params
    after = filters.get("published_after")
    before = filters.get("published_before")
    if after:
        clauses.append(f"{alias}.published_at >= ?")
        params.append(str(after))
    if before:
        clauses.append(f"{alias}.published_at <= ?")
        params.append(str(before))
    cats = [int(x) for x in (filters.get("category_ids") or []) if str(x).lstrip("-").isdigit()]
    if cats:
        clauses.append(f"{alias}.category_id IN ({','.join('?' * len(cats))})")
        params.extend(cats)
    return (" AND " + " AND ".join(clauses)) if clauses else "", params


class IndexStore:
    def __init__(self, path: str = ":memory:", read_only: bool = True, cache_mb: int = 128):
        self.path = path
        memory = path == ":memory:"
        self.read_only = read_only and not memory
        if self.read_only:
            uri = f"file:{path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(f"PRAGMA cache_size=-{int(cache_mb) * 1024}")
        self.conn.execute("PRAGMA foreign_keys=ON")
        if self.read_only:
            self.conn.execute("PRAGMA query_only=1")
        if memory:
            self._apply_schema()

    @classmethod
    def create(cls, path: str, cache_mb: int = 128) -> IndexStore:
        """Open (or create) a writable index and apply the schema."""
        store = cls(path, read_only=False, cache_mb=cache_mb)
        if path != ":memory:":
            store.conn.execute("PRAGMA page_size=8192")
            store.conn.execute("PRAGMA journal_mode=WAL")
        store._apply_schema()
        return store

    def _apply_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL + TRIGGERS_SQL)
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # -- search ------------------------------------------------------------

    def lexical(
        self,
        match: str,
        top_n: int,
        filters: dict | None = None,
        title_weight: float = 3.0,
        overfetch: int = 10,
    ) -> list[Hit]:
        """Rank chunks by BM25 for an FTS5 MATCH expression.

        Ranking happens inside the FTS subquery *before* joining `chunks`:
        joining first makes SQLite look up every matching row (130k for a
        term like "rwanda") instead of the top N. With filters we over-fetch
        and filter the ranked slice; if that leaves too few rows we fall
        back to the exact (slow) filtered query.
        """
        if not match.strip():
            return []
        where, params = _filter_sql(filters)
        limit = top_n * overfetch if where else top_n
        sql = (
            "SELECT f.rowid AS cid, f.s, c.wp_id, c.published_day FROM ("
            "SELECT rowid, bm25(chunks_fts, ?, 1.0) AS s FROM chunks_fts "
            "WHERE chunks_fts MATCH ? ORDER BY s LIMIT ?) f "
            f"JOIN chunks c ON c.cid = f.rowid WHERE 1=1{where} ORDER BY f.s LIMIT ?"
        )
        try:
            rows = self.conn.execute(sql, [title_weight, match, limit, *params, top_n]).fetchall()
            if where and len(rows) < min(top_n, 20):
                exact = (
                    "SELECT f.rowid AS cid, bm25(chunks_fts, ?, 1.0) AS s, c.wp_id, "
                    "c.published_day FROM chunks_fts f JOIN chunks c ON c.cid = f.rowid "
                    f"WHERE chunks_fts MATCH ?{where} ORDER BY s LIMIT ?"
                )
                rows = self.conn.execute(exact, [title_weight, match, *params, top_n]).fetchall()
        except sqlite3.Error:
            # Malformed MATCH syntax for exotic input: no lexical support.
            return []
        return [Hit(r["cid"], float(r["s"]), r["wp_id"], r["published_day"]) for r in rows]

    def newest(self, top_n: int, filters: dict | None = None) -> list[Hit]:
        """Most recent articles (first chunk each), for browse-mode questions."""
        where, params = _filter_sql(filters)
        rows = self.conn.execute(
            "SELECT c.cid, c.wp_id, c.published_day FROM chunks c "
            f"WHERE c.chunk_index = 0{where} ORDER BY c.published_at DESC LIMIT ?",
            [*params, top_n],
        ).fetchall()
        return [Hit(r["cid"], 0.0, r["wp_id"], r["published_day"]) for r in rows]

    # -- lookups -----------------------------------------------------------

    def get_chunks(self, cids: Sequence[int] | Iterable[int]) -> dict[int, dict]:
        ids = list(dict.fromkeys(int(c) for c in cids))
        out: dict[int, dict] = {}
        for i in range(0, len(ids), 500):
            batch = ids[i : i + 500]
            rows = self.conn.execute(
                f"SELECT {CHUNK_COLUMNS} FROM chunks WHERE cid IN ({','.join('?' * len(batch))})",
                batch,
            ).fetchall()
            for r in rows:
                out[r["cid"]] = dict(r)
        return out

    def chunks_for_article(self, wp_id: int) -> list[dict]:
        rows = self.conn.execute(
            f"SELECT {CHUNK_COLUMNS} FROM chunks WHERE wp_id = ? ORDER BY chunk_index",
            (int(wp_id),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_article(self, wp_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT wp_id, title, published_at, url, body, status FROM articles WHERE wp_id = ?",
            (int(wp_id),),
        ).fetchone()
        if not row or row["status"] != "ok":
            return None
        return {
            "wp_id": row["wp_id"],
            "title": row["title"],
            "published_at": row["published_at"],
            "url": row["url"],
            "body": row["body"] or "",
        }

    def get_articles(self, wp_ids: Iterable[int]) -> dict[int, dict]:
        ids = list(dict.fromkeys(int(w) for w in wp_ids))
        out: dict[int, dict] = {}
        for i in range(0, len(ids), 500):
            batch = ids[i : i + 500]
            rows = self.conn.execute(
                "SELECT wp_id, title, published_at, url FROM articles "
                f"WHERE status = 'ok' AND wp_id IN ({','.join('?' * len(batch))})",
                batch,
            ).fetchall()
            for r in rows:
                out[r["wp_id"]] = dict(r)
        return out

    # -- meta --------------------------------------------------------------

    def meta(self) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self.conn.execute("SELECT key, value FROM meta")}

    def set_meta(self, **values) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            [(k, str(v)) for k, v in values.items()],
        )
        self.conn.commit()

    def stats(self) -> dict:
        articles = self.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE status = 'ok'"
        ).fetchone()[0]
        chunks = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        newest = self.conn.execute(
            "SELECT MAX(published_at) FROM articles WHERE status = 'ok'"
        ).fetchone()[0]
        modified = self.conn.execute("SELECT MAX(modified_at) FROM articles").fetchone()[0]
        return {
            "articles": articles,
            "chunks": chunks,
            "max_published_at": newest or "",
            "max_modified_at": modified or "",
        }
