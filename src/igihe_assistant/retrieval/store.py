"""Portable retrieval backend: SQLite FTS5 lexical + in-memory dense."""

from __future__ import annotations

import sqlite3
from typing import Protocol


class RetrievalBackend(Protocol):
    def index(self, chunks: list[dict], vectors: dict[str, list[float]]) -> None: ...

    def lexical(
        self, query: str, top_n: int, filters: dict | None = None
    ) -> list[tuple[str, float]]:
        """Return (chunk_id, score) ranked best-first."""

    def dense(
        self, query_vec: list[float], top_n: int, filters: dict | None = None
    ) -> list[tuple[str, float]]: ...


def _passes(chunk: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    if filters.get("category_ids") and chunk.get("category_id") not in filters["category_ids"]:
        # Also accept category label match for fixture mode.
        if chunk.get("category") not in filters["category_ids"]:
            return False
    after = filters.get("published_after")
    before = filters.get("published_before")
    pub = chunk.get("published_at", "")
    if after and pub < str(after):
        return False
    if before and pub > str(before):
        return False
    return True


class SqliteBackend:
    def __init__(self, path: str = ":memory:"):
        # The serving layer may query from a different thread than the one
        # that built the index (e.g. ASGI/test portals); reads after the
        # initial bulk index are safe to share. Rebuild per process instead.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(id, text)")
        self.chunks: dict[str, dict] = {}
        self.vectors: dict[str, list[float]] = {}

    def index(self, chunks: list[dict], vectors: dict[str, list[float]]) -> None:
        self.conn.execute("DELETE FROM fts")
        for ch in chunks:
            self.chunks[ch["id"]] = ch
            self.conn.execute(
                "INSERT INTO fts(id, text) VALUES (?, ?)",
                (ch["id"], f"{ch.get('title', '')} {ch.get('heading', '')} {ch['content']}"),
            )
            if ch["id"] in vectors:
                self.vectors[ch["id"]] = vectors[ch["id"]]
        self.conn.commit()

    def lexical(
        self, query: str, top_n: int, filters: dict | None = None
    ) -> list[tuple[str, float]]:
        terms = [t.strip('"') for t in query.split() if t.strip('"')]
        if not terms:
            return []
        # Prefix match per term (typo/name tolerant baseline for the slice).
        match = " OR ".join(f'"{t}"*' for t in terms[:12])
        try:
            rows = self.conn.execute(
                "SELECT id, rank FROM fts WHERE fts MATCH ? ORDER BY rank LIMIT ?",
                (match, top_n * 3),
            ).fetchall()
        except sqlite3.Error:
            # Malformed MATCH syntax for exotic input: no lexical support.
            return []
        out = []
        for cid, rank in rows:
            ch = self.chunks.get(cid)
            if ch and _passes(ch, filters):
                out.append((cid, -float(rank)))
            if len(out) >= top_n:
                break
        return out

    def dense(
        self, query_vec: list[float], top_n: int, filters: dict | None = None
    ) -> list[tuple[str, float]]:
        scored = []
        for cid, vec in self.vectors.items():
            ch = self.chunks.get(cid)
            if ch and _passes(ch, filters):
                scored.append((cid, sum(a * b for a, b in zip(query_vec, vec, strict=True))))
        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored[:top_n]


class PostgresBackend:
    """Production adapter stub: requires live PostgreSQL + pgvector."""

    def __init__(self, dsn: str = ""):
        self.dsn = dsn

    def _unavailable(self):
        raise RuntimeError("postgres backend unavailable (no live DB in fixture mode)")

    def index(self, chunks, vectors):
        self._unavailable()

    def lexical(self, query, top_n, filters=None):
        self._unavailable()

    def dense(self, query_vec, top_n, filters=None):
        self._unavailable()
