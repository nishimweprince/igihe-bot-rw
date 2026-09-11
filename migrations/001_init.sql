-- Production schema parity (PostgreSQL 16+ with pgvector/pg_trgm/unaccent).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS articles (
  wp_id bigint PRIMARY KEY,
  slug text, canonical_url text UNIQUE,
  status text, published_at timestamptz, modified_at timestamptz,
  title_original text, title_normalized text,
  excerpt_original text, body_original text, body_normalized text,
  author_ids bigint[], category_ids bigint[], tag_ids bigint[],
  featured_media_id bigint, language text DEFAULT 'rw',
  content_sha256 text, raw_object_key text,
  extraction_version text, ingested_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS article_chunks (
  id uuid PRIMARY KEY, wp_id bigint REFERENCES articles(wp_id) ON DELETE CASCADE,
  chunk_index integer, heading text, content text, content_normalized text,
  paragraph_start integer, paragraph_end integer,
  embedding vector(1024), embedding_model text, embedding_version text,
  token_count integer, search_document tsvector, created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS authors (id bigint PRIMARY KEY, name text, link text);
CREATE TABLE IF NOT EXISTS categories (id bigint PRIMARY KEY, name text, slug text);
CREATE TABLE IF NOT EXISTS tags (id bigint PRIMARY KEY, name text, slug text);
CREATE TABLE IF NOT EXISTS ingestion_runs (
  run_id uuid PRIMARY KEY, started_at timestamptz, finished_at timestamptz,
  code_version text, extraction_version text, fetched integer,
  changed integer, unchanged integer, failed integer
);
CREATE TABLE IF NOT EXISTS ingestion_failures (
  id bigserial PRIMARY KEY, run_id uuid REFERENCES ingestion_runs(run_id),
  wp_id bigint, reason text, detail text
);
CREATE TABLE IF NOT EXISTS model_registry (
  model_id text PRIMARY KEY, revision text, dim integer,
  tokenizer text, checksum text
);
CREATE TABLE IF NOT EXISTS evaluation_runs (
  run_id uuid PRIMARY KEY, dataset_version text, config jsonb,
  metrics jsonb, created_at timestamptz DEFAULT now()
);
CREATE TABLE IF NOT EXISTS feedback_events (
  id bigserial PRIMARY KEY, session_id text, helpful boolean,
  reason text, created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_articles_pub ON articles (published_at);
CREATE INDEX IF NOT EXISTS idx_articles_mod ON articles (modified_at);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles (status);
CREATE INDEX IF NOT EXISTS idx_chunks_wp ON article_chunks (wp_id);
CREATE INDEX IF NOT EXISTS idx_chunks_fts ON article_chunks USING gin (search_document);
CREATE INDEX IF NOT EXISTS idx_title_trgm ON articles USING gin (title_normalized gin_trgm_ops);
