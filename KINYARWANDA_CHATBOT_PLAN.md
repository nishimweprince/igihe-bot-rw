# IGIHE Kinyarwanda News Assistant: Implementation Plan

Status: planning reference  
Audience: IGIHE engineering, product, editorial, infrastructure, and security teams  
Initial deployment target: Ubuntu Linux, local Ollama APIs, CPU-first pilot  
Expected site traffic: approximately 100,000 visits per day; chatbot usage must be measured separately  
Last updated: 2026-09-11

## 1. Executive decision summary

Build the assistant as a retrieval-augmented generation (RAG) system, not as a
model trained to memorize the article archive.

The system should:

1. Extract IGIHE articles from the `old.igihe.com` WordPress REST API.
2. retain an immutable local copy of each source response;
3. clean, normalize, deduplicate, and split each article into retrievable
   passages;
4. index those passages using both lexical search and multilingual vector
   embeddings;
5. retrieve and rerank evidence for every reader question;
6. send only that evidence to a locally hosted Llama model through Ollama;
7. answer in Kinyarwanda with article-level citations; and
8. explicitly decline to answer when the archive does not contain sufficient
   evidence.

Use PostgreSQL 16 or newer with the `pgvector`, `pg_trgm`, and `unaccent`
extensions as the primary database. PostgreSQL is the best starting choice for
this corpus because it provides transactions, metadata filtering, full-text
search, vector search, migrations, backups, and familiar operational tooling in
one service. A separate vector database is not justified until measurements
show that PostgreSQL is the bottleneck.

Create a new private, company-owned repository, provisionally named
`igihe-rw-assistant`. Treat the current `igihe-ai-reader` repository as a UI and
product prototype. Do not commit the full article corpus, generated embeddings,
database snapshots, user conversations, or secrets to either repository.

ALTA Tokenizer should initially be an isolated research experiment, not part of
the production request path. The tokenizer used to count and truncate chunks
must match the selected embedding model, and the tokenizer used to construct the
generation prompt must match the selected Llama model. ALTA becomes a core
component only if IGIHE chooses to train a Kinyarwanda model from scratch or
substantially retrain its token embeddings.

## 2. Context verified during discovery

The following observations define the starting point:

- `old.igihe.com` exposes a public WordPress REST API at
  `/wp-json/wp/v2/posts`.
- The API reported 202,756 posts and 2,028 pages when requested with
  `per_page=100` on 2026-09-11.
- The earliest public post returned by an ascending date query was dated
  2010-05-18.
- A 100-article sample distributed across the archive had a median rendered
  HTML length of approximately 2,495 characters and a mean of approximately
  3,288 characters. The complete raw text corpus is therefore moderate in size
  and is suitable for a single PostgreSQL deployment.
- The current demo contains only 55 Kinyarwanda articles and passes one full
  article or excerpts from the latest 14 articles directly to an LLM. That is a
  valid prototype behavior but is not archive-wide retrieval.
- The current repository is a Next.js application. The proposed extraction and
  local embedding stack is better implemented as a Python 3.12 service or job.
- The development machine's default Python is 3.9.6. The new project should use
  a containerized and pinned Python runtime rather than relying on the host
  Python installation.

These counts are planning inputs, not permanent invariants. The ingestion job
must read WordPress response headers and record actual counts on every run.

## 3. Product goals

### 3.1 Primary goals

- Let a reader ask natural Kinyarwanda questions about IGIHE's current and
  historical reporting.
- Ground every factual answer in retrievable IGIHE articles.
- Show sources that open the original IGIHE article.
- Preserve editorial trust by avoiding unsupported claims.
- Keep the corpus, embeddings, retrieval service, and Llama inference on IGIHE
  infrastructure.
- Support incremental ingestion when articles are published, corrected,
  unpublished, or deleted.
- Provide reproducible evaluation so that model and retrieval changes can be
  compared before release.
- Start on CPU hardware without making CPU-only inference a permanent
  production assumption.

### 3.2 Secondary goals

- Support mixed Kinyarwanda and English names, acronyms, quotations, and
  numbers.
- Allow date, category, author, and article filters.
- Provide a small integration API usable by the production IGIHE frontend.
- Capture privacy-preserving feedback for retrieval and answer improvement.
- Make the index fully rebuildable from retained source snapshots.

### 3.3 Non-goals for the first production release

- Training a foundation model from scratch.
- Replacing IGIHE's site search in the first iteration.
- Answering general-knowledge questions not covered by IGIHE.
- Autonomous publishing, article editing, or editorial recommendations.
- Voice transcription or text-to-speech. These can be added after text quality
  and capacity are proven.
- Fine-tuning Llama on the entire archive to memorize news facts.

## 4. Important terminology

"Local" has three independent meanings in this project:

1. **Local corpus:** article source data is stored on IGIHE-controlled
   infrastructure.
2. **Local retrieval:** embeddings and search indexes are created and queried
   on IGIHE-controlled infrastructure.
3. **Local generation:** prompts are processed by Ollama/Llama on
   IGIHE-controlled infrastructure.

This plan assumes all three. Article ingestion is not model training. The
archive is indexed and retrieved at question time. Future fine-tuning, if any,
should improve language behavior or retrieval relevance rather than encode
facts that may later be corrected.

## 5. Proposed architecture

```mermaid
flowchart LR
    Reader[Reader browser] --> Proxy[Reverse proxy / rate limiter]
    Proxy --> Web[IGIHE frontend / chat widget]
    Web --> API[Assistant API]
    API --> QueryEmbed[Query embedding]
    QueryEmbed --> PG[(PostgreSQL + pgvector)]
    PG --> Rerank[Optional local reranker]
    Rerank --> Context[Evidence and context builder]
    Context --> Ollama[Ollama / Llama]
    Ollama --> Validate[Citation and response validator]
    Validate --> Web

    Timer[systemd timer or cron] --> Ingest[Ingestion worker]
    Ingest --> WP[old.igihe.com WordPress API]
    Ingest --> Raw[(Compressed raw snapshots)]
    Ingest --> Clean[Cleaner and chunker]
    Clean --> DocEmbed[Document embedding]
    DocEmbed --> PG
```

### 5.1 Runtime components

- **Frontend/chat widget:** the reader-facing component in the production
  website. It streams answers, renders citations, and collects explicit
  feedback.
- **Assistant API:** validates requests, performs retrieval, builds prompts,
  calls Ollama, validates the output, and emits a streaming response.
- **Ingestion worker:** performs the initial archive backfill and incremental
  synchronization.
- **Embedding runtime:** loads the selected multilingual embedding model. It may
  run inside the Python API for the pilot and become a dedicated service if
  concurrency requires it.
- **Optional reranker:** rescores a small candidate set after hybrid retrieval.
  It should be disabled initially if CPU latency outweighs measured quality
  gains.
- **PostgreSQL:** stores canonical articles, chunks, vectors, metadata,
  ingestion state, model versions, and non-sensitive operational events.
- **Raw snapshot storage:** compressed WordPress responses retained on local
  disk for the pilot and on backed-up S3-compatible storage, such as MinIO, for
  production.
- **Ollama:** serves the pinned, quantized Llama generation model through the
  local network only.
- **Reverse proxy:** terminates TLS, applies request-size and rate limits, and
  exposes only the frontend/API paths required by the site.

### 5.2 Recommended technology baseline

| Concern | Initial choice | Reason |
| --- | --- | --- |
| API and ingestion | Python 3.12, FastAPI, Pydantic | Mature local ML ecosystem and typed API contracts |
| Dependency management | `uv` with a committed lockfile | Reproducible and fast container builds |
| Database | PostgreSQL 16+ | Metadata, transactions, backups, and search in one system |
| Vector indexing | `pgvector` HNSW with cosine distance | Appropriate for the expected corpus size and incremental updates |
| Lexical indexing | PostgreSQL `tsvector` using the `simple` configuration | Avoids applying an English stemmer to Kinyarwanda |
| Typo tolerance | `pg_trgm` on normalized title and body fields | Helps with spelling and name variants |
| Raw storage | gzip-compressed JSON on backed-up local/object storage | Auditable and reproducible extraction |
| Local embeddings | Benchmark BGE-M3 and multilingual E5 | Both are multilingual; Kinyarwanda quality must be measured locally |
| Local generation | A quantized instruction-tuned Llama served by Ollama | Matches the stated on-premise requirement |
| Scheduling | systemd timer or cron invoking an idempotent CLI | Simpler than introducing a queue during the pilot |
| Reverse proxy | Existing IGIHE proxy, otherwise Nginx or Caddy | TLS, buffering, limits, and streaming support |
| Metrics | Prometheus-compatible metrics plus existing company monitoring | Capacity and quality visibility |
| Load testing | k6 or Locust | Reproducible concurrent and streaming tests |

Do not introduce Kubernetes, Kafka, a separate vector database, or a distributed
task queue during the pilot unless they are already organizational standards.

## 6. Repository strategy

### 6.1 Recommended repository

Create `igihe-rw-assistant` as a private repository in the IGIHE organization.
Use a monorepo so that the API, ingestion code, evaluation suite, migrations,
and local integration demo remain versioned together.

```text
igihe-rw-assistant/
├── README.md
├── PLAN.md
├── SECURITY.md
├── CONTRIBUTING.md
├── .env.example
├── docker-compose.yml
├── pyproject.toml
├── uv.lock
├── apps/
│   ├── api/                 # FastAPI request and streaming endpoints
│   └── demo-web/            # Optional Next.js integration harness
├── src/igihe_assistant/
│   ├── config/
│   ├── ingestion/
│   ├── extraction/
│   ├── normalization/
│   ├── chunking/
│   ├── embeddings/
│   ├── retrieval/
│   ├── reranking/
│   ├── prompting/
│   ├── generation/
│   └── observability/
├── migrations/
├── evals/
│   ├── datasets/
│   ├── scorers/
│   └── reports/             # Summary reports only, no sensitive logs
├── tests/
│   ├── fixtures/            # Small approved article samples
│   ├── unit/
│   ├── integration/
│   └── load/
├── scripts/
└── docs/
    ├── architecture.md
    ├── operations.md
    ├── data-governance.md
    └── decision-log.md
```

### 6.2 Relationship to the current repository

- Reuse product ideas and approved UI components, not the current JSON-based
  storage architecture.
- Keep the production retrieval API independent of Next.js so it can be scaled,
  tested, and deployed without rebuilding the website.
- Integrate the production site through a small versioned HTTP contract.
- Preserve the current repository as evidence of the initial product concept.
- Do not copy secrets, generated data, or company content between repositories.

## 7. Data model

The exact schema should be implemented through migrations. The following is the
minimum logical model.

### 7.1 `articles`

| Column | Purpose |
| --- | --- |
| `wp_id bigint primary key` | Stable WordPress identity |
| `slug text` | Current public slug |
| `canonical_url text` | Link presented in citations |
| `status text` | Published, removed, unavailable, or quarantined |
| `published_at timestamptz` | Original publication time |
| `modified_at timestamptz` | WordPress modification time |
| `title_original text` | Faithful rendered title |
| `title_normalized text` | Search-normalized title |
| `excerpt_original text` | Original excerpt text |
| `body_original text` | Cleaned, reader-visible content |
| `body_normalized text` | Normalized search copy |
| `author_ids bigint[]` | WordPress author references |
| `category_ids bigint[]` | WordPress category references |
| `tag_ids bigint[]` | WordPress tag references |
| `featured_media_id bigint` | Optional media reference |
| `language text` | Detected or source language, initially `rw` |
| `content_sha256 text` | Idempotency and change detection |
| `raw_object_key text` | Location of the retained source snapshot |
| `extraction_version text` | Cleaner version that created the text |
| `ingested_at timestamptz` | Audit timestamp |

### 7.2 `article_chunks`

| Column | Purpose |
| --- | --- |
| `id uuid primary key` | Stable chunk identifier |
| `wp_id bigint` | Parent article |
| `chunk_index integer` | Order in the article |
| `heading text` | Nearest section heading |
| `content text` | Original evidence shown to the model |
| `content_normalized text` | Lexical search copy |
| `paragraph_start integer` | Traceability to article structure |
| `paragraph_end integer` | Traceability to article structure |
| `embedding vector(N)` | Model-dependent dense representation |
| `embedding_model text` | Exact model identifier and revision |
| `embedding_version text` | Pipeline version |
| `token_count integer` | Count from the embedding model tokenizer |
| `search_document tsvector` | Weighted title, heading, and body terms |
| `created_at timestamptz` | Audit timestamp |

### 7.3 Supporting tables

- `authors`, `categories`, and `tags` for WordPress metadata.
- `ingestion_runs` for start/end time, cursors, counts, failures, and versions.
- `ingestion_failures` for retryable and terminal errors.
- `model_registry` for immutable model names, revisions, dimensions, prompt
  formats, quantization, and checksums.
- `evaluation_runs` for dataset version, configuration, metrics, and artifacts.
- `feedback_events` for consented ratings and source selections. Avoid storing
  raw user text by default.

### 7.4 Indexes

- Unique index on `articles.wp_id` and `canonical_url`.
- B-tree indexes on publication time, modification time, status, category, and
  author fields.
- GIN index on `article_chunks.search_document`.
- Trigram indexes on normalized titles and optionally short normalized fields.
- HNSW cosine index on chunk embeddings after the embedding choice is fixed.
- Foreign keys with cascading chunk deletion when an article is removed or
  reprocessed.

Keep original and normalized text separately. Search normalization must never
alter the evidence displayed to readers or sent as a quotation.

## 8. Extraction and local storage pipeline

### 8.1 Source endpoints

The primary source is:

```text
GET https://old.igihe.com/wp-json/wp/v2/posts
```

Request only necessary fields during bulk synchronization:

```text
id,slug,status,date,modified,link,title,excerpt,content,
author,categories,tags,featured_media
```

Also synchronize the author, category, tag, and media metadata required for
filtering and citations. Avoid fetching each public HTML page when
`content.rendered` is complete. Fetch a page only as a recorded fallback when
the REST content is empty or known to be malformed.

### 8.2 Initial backfill algorithm

1. Start an `ingestion_runs` record containing the code version, extraction
   version, WordPress count headers, and start timestamp.
2. Request posts in deterministic ascending order with `per_page=100`.
3. Use low concurrency initially, such as two to four requests, with a clear
   IGIHE-specific user agent and contact identifier.
4. Retry network failures and `429`/`5xx` responses with exponential backoff and
   jitter. Respect `Retry-After` when present.
5. Write every successful WordPress record to an immutable gzip-compressed JSON
   object before parsing it.
6. Calculate and record a SHA-256 hash of the canonical source fields.
7. Upsert the article manifest using `wp_id` as the identity.
8. Submit changed records to extraction, normalization, chunking, and embedding.
9. Commit progress after each page so a stopped backfill resumes without
   repeating the entire run.
10. Reconcile the number of unique stored IDs with WordPress response headers.
11. Record permanent parse failures separately; do not silently count them as
    success.

Page-number pagination can shift while editors publish content. Make the
backfill idempotent, deduplicate on `wp_id`, and run a second modified-time sweep
after the first pass. If the API supports stable `orderby=id` behavior in the
target environment, prefer it for the initial pass and record the last observed
ID as additional audit information.

### 8.3 Incremental synchronization

Run an incremental job every 5 to 15 minutes during the pilot:

1. Read the last successful high-water `modified_at` timestamp.
2. Query posts ordered by modification time with a small overlap window, such
   as the previous 15 minutes.
3. Deduplicate by `wp_id` and compare the source hash.
4. For a changed article, transactionally replace its cleaned representation,
   chunks, lexical index, and embeddings.
5. Periodically reconcile recently published IDs and a small random archive
   sample to detect missed edits.
6. Run a daily deletion/unpublish reconciliation. Mark content unavailable
   before deleting retained snapshots, following IGIHE's retention policy.

The overlap window is essential because network failures, timestamp precision,
and concurrent editorial updates can otherwise create gaps.

### 8.4 Raw storage layout

For the CPU pilot on one Ubuntu host:

```text
/var/lib/igihe-assistant/raw/posts/YYYY/MM/<wp_id>/<modified_epoch>.json.gz
/var/lib/igihe-assistant/raw/manifests/<ingestion_run_id>.json
/var/lib/igihe-assistant/evals/<evaluation_run_id>/
```

Production storage should be on an encrypted, backed-up volume or a local
S3-compatible service. The database stores the object key and checksum. Never
serve raw objects directly to users.

### 8.5 HTML extraction

Use a real HTML parser such as `lxml` or Beautiful Soup. Do not parse article
HTML with regular expressions.

Extraction order:

1. HTML entity decode.
2. Remove scripts, styles, forms, tracking markup, share buttons, advertisements,
   navigation, and known boilerplate.
3. Preserve headings, paragraphs, block quotes, lists, captions, and meaningful
   link text.
4. Preserve paragraph boundaries and article order.
5. Convert line-break-only layouts into paragraphs conservatively.
6. Retain image captions as attributed text, but do not perform OCR initially.
7. Remove empty or repeated boilerplate paragraphs.
8. Compare extracted length and paragraph count against the rendered source.
9. Quarantine suspiciously empty or enormous records for review.

Create regression fixtures for at least:

- a normal text article;
- an article with video embeds;
- a photo-heavy article with captions;
- opinion/editorial content;
- a short announcement;
- malformed legacy HTML;
- tables and lists;
- mixed Kinyarwanda and English text; and
- an updated/corrected article.

### 8.6 Text normalization

Preserve a faithful original field and create a separate search-normalized copy.
The normalization pipeline should:

- use Unicode NFC;
- normalize non-breaking spaces and repeated whitespace;
- standardize typographic apostrophes and quotation marks only in the search
  copy;
- retain digits, currency symbols, initials, acronyms, and hyphenated names;
- lowercase only the search copy;
- optionally create an accent-folded search field, after measuring whether it
  improves Kinyarwanda queries;
- avoid English stemming and stop-word removal; and
- version every normalization change so the corpus can be rebuilt.

Do not translate Kinyarwanda articles into English before indexing. Translation
adds cost, creates factual drift, and weakens exact phrase retrieval.

### 8.7 Deduplication

Use three levels:

1. Exact identity by WordPress post ID.
2. Exact content equality by normalized SHA-256 hash.
3. Optional near-duplicate detection with SimHash or MinHash for syndicated or
   republished articles.

Near-duplicates should remain separate source articles but may be grouped during
retrieval so that one repeated story does not occupy every evidence slot.

## 9. Chunking strategy

Chunking must be article-aware and model-aware.

### 9.1 Initial parameters

- Target approximately 350 to 600 tokens per chunk using the embedding model's
  tokenizer.
- Use approximately 60 to 100 tokens of overlap only when a paragraph boundary
  would otherwise remove necessary context.
- Never split a sentence solely to hit an exact token target.
- Prepend the title, category, publication date, and nearest heading to the text
  embedded for retrieval.
- Store only the evidence body as the citable passage.
- Keep an entire short article as one chunk.
- Split very long paragraphs by sentence boundaries.

The embedding model may accept thousands of tokens, but large chunks typically
reduce passage precision and waste generation context. Final sizes must be
selected through retrieval evaluation, not compression ratio alone.

### 9.2 Stable chunk identity

Generate a chunk UUID from the article ID, extraction version, chunk index, and
content hash. This permits reproducible rebuilds and detects changed chunks.

### 9.3 Tokenizer rule

- Use the embedding model tokenizer to enforce embedding input limits.
- Use the selected Llama tokenizer to pack the Ollama prompt.
- Do not use character counts as a substitute for either limit.
- Do not use ALTA token counts to truncate input for a model that does not use
  the ALTA vocabulary.

## 10. Embedding model selection

Kinyarwanda is a low-resource language, so broad multilingual claims are not
sufficient evidence. Run a local bake-off before indexing the full archive.

### 10.1 Initial candidates

- BGE-M3: strong candidate for multilingual dense retrieval and long input;
  produces 1,024-dimensional embeddings and also supports sparse and
  multi-vector approaches.
- Multilingual E5 base or large: mature comparison baseline. The base model may
  be more suitable for CPU query latency; the large model may provide better
  quality at higher cost.
- One additional model already approved or used within IGIHE, if applicable.

Start with dense vectors plus PostgreSQL lexical search. Do not use BGE-M3's
additional sparse/ColBERT outputs until the simpler hybrid baseline has been
measured.

### 10.2 Bake-off dataset

Create at least 100 editor-reviewed query-to-article judgments:

- 60 direct factual questions;
- 10 exact-name or spelling-sensitive questions;
- 10 date/time questions;
- 10 questions requiring two articles; and
- 10 deliberately unanswerable questions.

Include old and recent articles and several editorial categories. A fluent
Kinyarwanda reviewer must identify all acceptable supporting articles, not just
one expected result.

### 10.3 Selection metrics

- Recall@5 and Recall@10.
- Mean reciprocal rank.
- nDCG@10 when multiple articles are relevant.
- CPU query-embedding latency.
- indexing throughput and peak memory.
- embedding storage size.
- behavior on spelling variants, named entities, and mixed-language queries.

Provisional retrieval acceptance target: at least 85% Recall@10 on the first
reviewed dataset, with no major editorial category below an agreed floor. The
final threshold must be approved after dataset quality is reviewed.

Record the exact model repository, commit/revision, tokenizer, pooling method,
prompt prefix, vector dimension, normalization method, and artifact checksum.
A change to any of these requires a new embedding version and evaluation run.

## 11. Hybrid retrieval and reranking

### 11.1 Candidate generation

For each query:

1. Validate and normalize the text.
2. Extract explicit date/category constraints without discarding the original
   query.
3. Generate a query embedding.
4. Retrieve the top 40 to 60 dense candidates.
5. Retrieve the top 40 to 60 lexical candidates using the PostgreSQL `simple`
   configuration, weighted title/heading/body fields, and optional trigram name
   matches.
6. Merge rankings using Reciprocal Rank Fusion (RRF).
7. Group excessive near-duplicates from the same story.
8. Optionally rerank the top 15 to 25 candidates with a local multilingual
   reranker.
9. Select approximately 5 to 8 diverse evidence chunks under the Llama context
   budget.

Hybrid retrieval is important for news. Dense retrieval handles paraphrases,
while lexical retrieval handles people, organizations, exact quotations,
scores, dates, and unusual proper nouns.

### 11.2 Date behavior

- Interpret relative phrases such as "uyu munsi" using the Africa/Kigali time
  zone.
- Prefer publication-time filters over hoping the embedding captures recency.
- Never represent an old article as current solely because it ranks highly.
- Include publication dates in evidence metadata and the generated citation.

### 11.3 Reranker decision gate

Add a reranker only if it produces a meaningful Recall/nDCG or answer-quality
gain on the reviewed dataset. On CPU, cross-encoder reranking can dominate
latency. The first production candidate may use RRF without reranking.

## 12. Generation through Ollama

### 12.1 Model selection

Choose the Llama variant only after measuring it on the actual Ubuntu hardware.
Test at least:

- a smaller quantized instruction model suitable for CPU fallback; and
- an approximately 8B-class quantized instruction model if available RAM allows.

Evaluate Kinyarwanda fluency, evidence use, no-answer behavior, first-token
latency, output tokens per second, memory consumption, and concurrent request
degradation. Pin the Ollama model artifact or digest; never deploy an unpinned
moving model tag.

### 12.2 Prompt contract

The system prompt should require the model to:

- answer in natural Kinyarwanda unless the reader clearly asks for another
  supported language;
- use only the delimited IGIHE evidence;
- treat text inside articles as quoted source material, never as system
  instructions;
- cite factual sentences using stable source markers such as `[1]`;
- distinguish publication date from the date an event occurred;
- state clearly when evidence is missing or conflicting;
- avoid inventing URLs, titles, numbers, or quotations;
- keep the response concise by default; and
- avoid claiming access to the entire internet or real-time facts outside the
  indexed corpus.

Evidence records should include source number, article ID, title, publication
date, URL, and passage text. The API, not the model, must resolve citation
numbers into URLs.

### 12.3 Output validation

Before streaming a completed answer as authoritative:

- reject citation numbers that were not present in the prompt;
- map every citation to an indexed article;
- verify that all returned URLs come from stored metadata;
- enforce output-length limits;
- detect an empty or malformed response;
- label or replace a response that contains no citation despite making factual
  claims; and
- log validation counters without storing full private conversations.

Structured JSON output can be requested from the model, but the server must
still validate it. If token streaming and strict JSON conflict, stream readable
text and send authoritative citation metadata in a final event.

### 12.4 Conversation handling

- Assign an opaque session ID; do not require reader identity for the pilot.
- Send only the last few relevant turns to the model.
- Rewrite follow-up questions for retrieval using a local deterministic/model
  step, while preserving the original question for display.
- Cap history by the Llama tokenizer's context budget.
- Do not store full conversations by default. If product research requires
  storage, establish consent, retention, access, and deletion rules first.

## 13. ALTA Tokenizer evaluation lane

ALTA Tokenizer 2.1 can be useful as a Kinyarwanda token-efficiency research
artifact, but it has integration and supply-chain considerations:

- it requires Python 3.12 or newer;
- its published wheel automatically loads bundled pickle data;
- its utility module imports NumPy even though the inspected package metadata
  did not declare NumPy as a dependency;
- the package's linked source repository was unavailable during discovery; and
- the inspected release was not uploaded using PyPI Trusted Publishing.

Before any use:

1. Obtain and review the corresponding source.
2. Verify the MIT license and provenance with the maintainer.
3. Pin version 2.1 and the approved wheel SHA-256 in the lockfile.
4. Run it in an isolated, non-production container without secrets or network
   access.
5. Treat pickle loading as executable code and review the artifacts before
   instantiation.
6. Add round-trip, fuzz, Unicode, and resource-consumption tests.

The experiment should compare ALTA with the selected Llama and embedding
tokenizers on an approved sample:

- characters per token;
- round-trip fidelity;
- encoding throughput;
- peak memory;
- names, apostrophes, currency, URLs, and mixed-language text; and
- morpheme fragmentation observed by fluent reviewers.

Stop after producing a report. Do not integrate ALTA into RAG chunking merely
because it compresses Kinyarwanda more efficiently. A later decision to build
an IGIHE-specific language model would be a separate research program with its
own compute, data, licensing, safety, and evaluation plan.

## 14. API contract

### 14.1 Reader request

```http
POST /v1/chat
Content-Type: application/json
```

```json
{
  "session_id": "opaque-client-session-id",
  "message": "Ni izihe nkuru IGIHE yanditse ku ...?",
  "article_id": null,
  "filters": {
    "published_after": null,
    "published_before": null,
    "category_ids": []
  }
}
```

### 14.2 Streaming response events

- `retrieval`: optional reader-safe indication that sources are being searched.
- `token`: answer text segments.
- `sources`: authoritative article IDs, titles, dates, and URLs.
- `done`: model/retrieval version and request ID.
- `error`: reader-safe Kinyarwanda message and opaque support ID.

Never expose raw prompts, stack traces, database errors, filesystem paths, or
Ollama internals to the browser.

### 14.3 Additional endpoints

- `GET /health/live`: process liveness only.
- `GET /health/ready`: database, embedding model, and Ollama readiness.
- `GET /v1/sources/{article_id}`: optional normalized citation metadata.
- `POST /v1/feedback`: explicit helpful/unhelpful feedback with a source reason.
- Internal authenticated endpoints for reindex status and evaluation; never
  expose them publicly.

Version the public API from the beginning.

## 15. Capacity and the 100,000-per-day requirement

One hundred thousand site visits per day is not automatically one hundred
thousand chatbot generations per day. Instrument these separately:

```text
daily chatbot messages = site visits
                       × chat activation rate
                       × messages per activated session
```

Example planning scenarios:

| Scenario | Activation | Messages/session | Messages/day | Average messages/sec |
| --- | ---: | ---: | ---: | ---: |
| Pilot adoption | 2% | 2 | 4,000 | 0.05 |
| Moderate adoption | 5% | 2 | 10,000 | 0.12 |
| Strong adoption | 10% | 3 | 30,000 | 0.35 |
| 100k means chat messages | n/a | n/a | 100,000 | 1.16 |

Averages hide the important problem: traffic peaks and each CPU generation may
occupy a model worker for many seconds. If 100,000 means chatbot messages rather
than site visits, a single CPU Ollama instance is unlikely to provide acceptable
interactive service without substantial queuing.

### 15.1 CPU-first controls

- Stream tokens immediately so readers see progress.
- Limit generated answer length.
- Set hard request, prompt, context, and generation timeouts.
- Use a bounded concurrency limit based on measured memory.
- Return a localized busy response instead of allowing an unbounded queue.
- Cache only safe, corpus-versioned responses to common non-personal questions.
- Cache query embeddings and retrieval results for normalized repeated queries.
- Keep document embedding out of the request path.
- Run ingestion and bulk indexing at low-priority/off-peak times.
- Isolate Ollama resources from PostgreSQL when possible.

### 15.2 Required load-test results

Before public rollout, record:

- first-token and completed-response latency at concurrency 1, 2, 4, 8, and the
  expected peak;
- Llama prompt and generation tokens per second;
- CPU utilization, RAM, swap, disk I/O, and temperature/throttling;
- query embedding and retrieval latency;
- database connection and cache behavior;
- timeout/error rate; and
- performance while incremental ingestion runs.

No response-time target has been supplied. The pilot must establish a baseline,
after which product and infrastructure owners should approve an SLO. A GPU,
additional Ollama replicas, a smaller model, or stricter admission control is a
release gate if CPU measurements fail that SLO.

## 16. Ubuntu deployment plan

### 16.1 Pilot topology

Use Docker Compose on one non-public Ubuntu host:

- `assistant-api`
- `ingestion-worker` using the same application image
- `postgres`
- `ollama`
- reverse proxy, unless provided externally
- metrics exporter(s)

Mount separate persistent volumes for PostgreSQL, Ollama models, raw snapshots,
and backups. Set CPU and memory limits carefully; do not allow ingestion to
starve the interactive API.

### 16.2 Production topology

Prefer at least these failure boundaries:

- PostgreSQL on durable storage with tested backups;
- Ollama on a compute host sized for the selected model;
- API replicas behind the existing reverse proxy; and
- ingestion on a worker that can be stopped without affecting queries.

If the organization has an established container platform, monitoring stack,
secret store, database service, or object store, adopt those standards instead
of duplicating them.

### 16.3 Configuration and secrets

Configuration should be environment-driven and documented in `.env.example`:

```text
DATABASE_URL=
RAW_STORAGE_ROOT=
WORDPRESS_BASE_URL=https://old.igihe.com
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=
EMBEDDING_MODEL=
EMBEDDING_MODEL_REVISION=
RERANKER_MODEL=
MAX_QUERY_CHARS=
MAX_CONTEXT_TOKENS=
MAX_OUTPUT_TOKENS=
MAX_CONCURRENT_GENERATIONS=
INGEST_CONCURRENCY=
LOG_CONTENT=false
```

Secrets must come from the organization's secret manager or protected runtime
environment. Ollama and PostgreSQL should not listen on public interfaces.

### 16.4 Backups and recovery

- Daily PostgreSQL backups with defined retention.
- PostgreSQL point-in-time recovery if organizational tooling supports it.
- Raw snapshot storage replicated or backed up separately.
- Monthly restore test, not just backup-job monitoring.
- Documented full reindex process from raw snapshots.
- Checksums for raw objects and model artifacts.
- Recovery time and recovery point objectives agreed before production.

## 17. Security, privacy, and editorial safeguards

### 17.1 Threats and controls

| Risk | Control |
| --- | --- |
| Prompt injection inside an article | Delimit evidence, declare it untrusted, provide no tools to the model, validate output |
| SQL injection | Parameterized queries and typed filters |
| Oversized requests | Proxy and API body/token limits |
| Denial of service against CPU inference | Per-IP/session rate limits, bounded concurrency, queue limits, timeouts |
| Malicious HTML | Parse and sanitize; never render source HTML in assistant output |
| Model artifact tampering | Pin revisions/digests and verify checksums |
| Dependency compromise | Lockfiles, image scanning, minimal containers, regular review |
| Private network exposure | Bind PostgreSQL/Ollama internally and restrict firewall rules |
| Sensitive conversation logging | Do not log raw text by default; redact and limit retention |
| Hallucinated sources | Server-owned citation mapping and validation |
| Removed/corrected content | Incremental sync, tombstones, and reindexing |

### 17.2 Reader privacy

- Do not require login unless the product specifically needs it.
- Do not combine chat questions with advertising or identity data without a
  separately approved policy.
- Store operational metrics without full question text where possible.
- If sampled conversations are needed for quality review, use explicit rules
  for consent, redaction, reviewer access, retention, and deletion.
- Treat IP addresses and session IDs according to the organization's privacy
  policy.

### 17.3 Editorial policy

Editorial leadership should define:

- which sections are in scope;
- whether sponsored, opinion, announcement, and archival content can be used;
- how corrections and contradictory reports are presented;
- whether older reporting requires an archive label;
- prohibited/high-risk question categories; and
- the exact wording for insufficient evidence and service unavailability.

## 18. Evaluation plan

### 18.1 Retrieval evaluation

Maintain a versioned dataset containing question, language, acceptable article
IDs, acceptable passage ranges, date/category constraints, and reviewer notes.
Measure Recall@5/10, MRR, nDCG, and slice results by question type and article
age.

### 18.2 End-to-end answer evaluation

For each test question, reviewers score:

- factual correctness;
- support from cited passages;
- citation completeness;
- Kinyarwanda fluency and terminology;
- relevance and concision;
- temporal correctness;
- no-answer correctness; and
- whether the answer misrepresents opinion as fact.

Suggested provisional release criteria:

- at least 85% retrieval Recall@10;
- at least 95% of returned citations resolve to an actual retrieved source;
- fewer than 5% unsupported factual claims in the reviewed release set;
- at least 90% correct refusal on intentionally unanswerable questions; and
- no critical editorial or privacy failures.

These thresholds are starting proposals. Report confidence intervals and raw
counts; do not hide regressions inside one aggregate score.

### 18.3 Automated checks

- Extraction fixture snapshots.
- Unicode normalization and apostrophe tests.
- Chunk boundary and token limit tests.
- Idempotent ingestion and update/delete tests.
- Retrieval regression tests with fixed model versions.
- Citation resolution and malformed-output tests.
- Prompt-injection and adversarial article fixtures.
- API contract, timeout, and rate-limit tests.
- Database migration and backup/restore tests.
- Load tests against the actual Ollama host.

### 18.4 Change policy

Any change to the embedding model, Llama model, prompt, chunking, normalization,
retrieval weights, reranker, or evidence count must produce a new evaluation
report compared with the current production baseline.

## 19. Observability and operations

### 19.1 Metrics

Track:

- requests, sessions, chat activation, and messages/session;
- success, refusal, busy, timeout, and error counts;
- time to first token and total response duration;
- prompt and completion token counts from the Llama tokenizer;
- embedding, dense search, lexical search, reranking, and generation duration;
- retrieved candidate counts and score distributions;
- citation and output validation failures;
- Ollama CPU/RAM and tokens/second;
- PostgreSQL connections, slow queries, cache, table/index size, and HNSW build
  status;
- ingestion lag, fetched/changed/unchanged/failed articles, and API rate errors;
  and
- explicit helpful/unhelpful feedback.

### 19.2 Logs

Use structured logs with request ID, model versions, corpus version, durations,
and error categories. Do not log full article bodies or user questions by
default. Maintain separate protected debug sampling only if approved.

### 19.3 Alerts

Alert on sustained API errors, Ollama unavailability, PostgreSQL saturation,
ingestion lag, disk usage, backup failures, rising citation-validation failures,
and unusual refusal/busy rates.

### 19.4 Runbooks

Document:

- Ollama/model restart;
- database restore;
- full and partial reindex;
- rollback to a previous model/prompt/corpus version;
- disabling chat while keeping the website available;
- WordPress API degradation;
- disk-full response; and
- handling a request to remove or correct an article.

## 20. Delivery phases and gates

Effort ranges below are indicative engineering days for one developer and must
be adjusted after infrastructure access and hardware inspection.

### Phase 0: alignment and baseline (1-2 days)

- Confirm ownership, repository, environments, and data policy.
- Clarify whether 100,000/day means site visits or chatbot messages.
- Inventory Ubuntu CPU cores, RAM, storage, and network.
- Select a small approved article sample and editorial reviewers.
- Record current demo behavior and desired production API contract.

**Gate:** architecture and success criteria approved.

### Phase 1: reproducible extraction (3-5 days)

- Create repository, containers, configuration, and migrations.
- Implement raw snapshot storage and WordPress client.
- Implement idempotent backfill, checkpoints, retry, and audit records.
- Build HTML extraction/normalization with legacy fixtures.
- Run a limited backfill, produce coverage and failure reports.

**Gate:** at least 99.5% of the approved sample extracts successfully, with all
failures visible and reproducible.

### Phase 2: retrieval baseline (4-7 days)

- Build the first Kinyarwanda retrieval evaluation set.
- Benchmark embedding candidates on CPU.
- Implement chunking, versioning, dense index, lexical index, and RRF.
- Tune chunk sizes and ranking using the evaluation set.
- Estimate full index time and storage from a representative slice.

**Gate:** selected embedding/retrieval configuration meets the approved
Recall@10 threshold and resource budget.

### Phase 3: grounded Ollama answers (3-6 days)

- Benchmark candidate quantized Llama variants.
- Implement prompt construction, token budgeting, streaming, refusal, and
  citation validation.
- Add multi-turn question rewriting with strict history limits.
- Complete end-to-end editor review.

**Gate:** answer-support, refusal, language-quality, and citation criteria pass.

### Phase 4: full backfill and operations (3-6 days plus indexing runtime)

- Backfill the full archive with controlled concurrency.
- Build HNSW and lexical indexes.
- Implement incremental sync and deletion reconciliation.
- Configure metrics, dashboards, alerts, backups, and runbooks.
- Perform restore and full-reindex exercises.

**Gate:** corpus reconciliation passes and recovery is demonstrated.

### Phase 5: frontend integration and controlled pilot (3-5 days)

- Integrate the versioned API with the production-like frontend.
- Add localized loading, busy, refusal, error, and feedback states.
- Run accessibility, mobile, security, and load tests.
- Release to staff or a small traffic percentage.
- Compare measured activation and load with planning assumptions.

**Gate:** editorial, infrastructure, security, and product owners approve wider
rollout.

### Phase 6: production ramp and optimization (ongoing)

- Increase traffic gradually with rollback controls.
- Expand the reviewed evaluation set from real failure categories.
- Decide whether CPU remains viable or GPU/replicas are required.
- Test reranking only if retrieval errors justify it.
- Consider retriever fine-tuning after sufficient reviewed query/article pairs
  exist.
- Reconsider voice, English/French support, and ALTA research only after the
  Kinyarwanda text path is stable.

## 21. Initial backlog

### Must have

- [ ] Company-owned private repository.
- [ ] Approved data and log retention rules.
- [ ] Dockerized Python 3.12 environment with lockfile.
- [ ] PostgreSQL, pgvector, pg_trgm, and migrations.
- [ ] Raw snapshot store with checksums.
- [ ] Resumable WordPress full and incremental ingestion.
- [ ] Parser fixtures and extraction coverage report.
- [ ] Versioned chunking and embedding pipeline.
- [ ] Kinyarwanda retrieval evaluation set.
- [ ] Hybrid retrieval with metadata/date filters.
- [ ] Ollama generation with streaming and bounded concurrency.
- [ ] Citation validation and no-evidence response.
- [ ] Load test on actual Ubuntu CPU hardware.
- [ ] Metrics, backups, restore test, and rollback runbook.
- [ ] Controlled pilot and editorial sign-off.

### Should have

- [ ] Near-duplicate grouping.
- [ ] Reader feedback with privacy controls.
- [ ] Query/result cache keyed by corpus and model versions.
- [ ] Staff evaluation interface.
- [ ] Optional local reranker based on measured gain.
- [ ] Recent-content freshness dashboard.

### Later/experimental

- [ ] Retrieval fine-tuning on reviewed Kinyarwanda query/article pairs.
- [ ] ALTA tokenizer benchmark report.
- [ ] Voice input/output.
- [ ] Multilingual answer support.
- [ ] OCR for text embedded in legacy images.
- [ ] GPU inference or multiple Ollama replicas.

## 22. Risks and tradeoffs

| Decision or risk | Benefit | Cost/mitigation |
| --- | --- | --- |
| RAG instead of factual fine-tuning | Current, traceable, removable facts | Requires reliable ingestion and retrieval |
| PostgreSQL + pgvector | One operational system; good metadata filtering | Vector-scale ceiling is lower than specialist systems; benchmark before changing |
| Hybrid retrieval | Better names, dates, and paraphrases | More ranking logic and evaluation |
| CPU-first Ollama | Low-cost, local pilot | Limited throughput and long generation latency; use admission control and keep GPU as a gate |
| Small Llama model | Faster and cheaper | May weaken Kinyarwanda fluency and evidence reasoning |
| Larger Llama model | Potentially stronger answers | More RAM and slower CPU generation |
| Frequent incremental ingestion | Fresh corrections and stories | More API/database work; use hashes and overlap windows |
| Raw source retention | Reproducibility and audits | Storage and retention obligations; compress and govern access |
| No raw chat logging | Stronger reader privacy | Harder debugging; use consented/redacted sampling if approved |
| Reranking | May improve precision | Can dominate CPU latency; require measured gain |
| ALTA experimentation | Kinyarwanda-specific research value | Not compatible with existing model vocabularies and needs provenance/security review |

## 23. Decisions still required

Record answers in `docs/decision-log.md` before production implementation:

1. Does 100,000/day mean total website visits, chatbot sessions, or chatbot
   messages?
2. What are the Ubuntu server's CPU model/core count, RAM, disk type/capacity,
   and available backup storage?
3. Which exact Llama variants and licenses are approved?
4. Is an internal GPU available for production if the CPU pilot fails capacity
   tests?
5. Which content types are in scope: news, opinions, sponsored content,
   announcements, videos, and photo stories?
6. Should the assistant cover only `old.igihe.com`, or also continuously ingest
   the current Kinyarwanda site?
7. What production frontend and authentication conventions must the API follow?
8. What retention policy applies to raw WordPress snapshots, operational logs,
   and optional user feedback?
9. Who are the editorial reviewers, and who has final authority over answer
   language and no-evidence wording?
10. Which monitoring, secret-management, container, database, and backup tools
    are already standard inside IGIHE?

## 24. Definition of done for the first public release

The project is ready for its first public release only when:

- the approved archive scope is locally stored, reconciled, and incrementally
  synchronized;
- every index is reproducible from retained source snapshots;
- retrieval and answer metrics meet approved thresholds on a versioned,
  editor-reviewed Kinyarwanda dataset;
- all factual answers expose valid IGIHE citations and unsupported questions
  produce the approved no-evidence response;
- the chosen Ollama/Llama model meets an approved SLO under measured peak load;
- rate limiting, bounded concurrency, timeouts, monitoring, backups, restore,
  rollback, and content-removal procedures are tested;
- privacy, security, infrastructure, product, and editorial owners have signed
  off; and
- the assistant can be disabled without disrupting the main IGIHE website.

