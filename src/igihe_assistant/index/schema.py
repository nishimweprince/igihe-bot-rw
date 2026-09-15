"""On-disk index schema: articles + chunks + FTS5 trigram over chunks.

Trigram tokenisation is the Kinyarwanda strategy: the language is
agglutinative, so whole-word BM25 fragments one lemma into dozens of
inflected forms. Character trigrams match any substring >= 3 chars with no
morphological model at all. The index is disk-resident (SQLite pages in a
small cache), so it is RAM-cheap and disk-heavy (~4-5x the text).
"""

from __future__ import annotations

SCHEMA_VERSION = "index-v1"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  slug TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS articles (
  wp_id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  published_at TEXT NOT NULL,
  published_day INTEGER NOT NULL,
  modified_at TEXT NOT NULL,
  category_id INTEGER,
  category_ids TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  body TEXT
);
CREATE INDEX IF NOT EXISTS articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS articles_modified ON articles(modified_at);

CREATE TABLE IF NOT EXISTS chunks (
  cid INTEGER PRIMARY KEY,
  chunk_uid TEXT NOT NULL UNIQUE,
  wp_id INTEGER NOT NULL REFERENCES articles(wp_id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  title TEXT NOT NULL,
  heading TEXT NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  published_at TEXT NOT NULL,
  published_day INTEGER NOT NULL,
  category_id INTEGER
);
CREATE INDEX IF NOT EXISTS chunks_wp ON chunks(wp_id);
CREATE INDEX IF NOT EXISTS chunks_published ON chunks(published_at);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  title, content,
  content='chunks', content_rowid='cid',
  tokenize="trigram remove_diacritics 1"
);
"""

# External-content FTS5 needs these to stay in sync with `chunks`. They are
# dropped during a bulk build (then the FTS table is rebuilt once) and kept
# on for incremental upserts.
TRIGGERS_SQL = """
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, title, content) VALUES (new.cid, new.title, new.content);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title, content)
    VALUES ('delete', old.cid, old.title, old.content);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, title, content)
    VALUES ('delete', old.cid, old.title, old.content);
  INSERT INTO chunks_fts(rowid, title, content) VALUES (new.cid, new.title, new.content);
END;
"""

DROP_TRIGGERS_SQL = """
DROP TRIGGER IF EXISTS chunks_ai;
DROP TRIGGER IF EXISTS chunks_ad;
DROP TRIGGER IF EXISTS chunks_au;
"""
