"""Shared fixture pipeline: posts -> chunks -> indexed backend."""

from __future__ import annotations

from .chunking.chunker import chunk_article
from .embeddings.embedder import FakeHashEmbedder
from .extraction.parser import extract, rendered_text, rendered_title
from .normalization.normalize import normalize_original, normalize_search
from .retrieval.store import SqliteBackend


def build_index(posts: list[dict], embedder=None):
    embedder = embedder or FakeHashEmbedder()
    backend = SqliteBackend()
    chunks: list[dict] = []
    articles: dict[int, dict] = {}
    for post in posts:
        wp_id = int(post["id"])
        title = rendered_title(post)
        parsed = extract(rendered_text(post))
        if parsed["status"] != "ok":
            continue
        body_original = "\n".join(t for _, t in parsed["blocks"])
        articles[wp_id] = {
            "wp_id": wp_id,
            "title": normalize_original(title),
            "published_at": post.get("date", ""),
            "url": post.get("link", ""),
            "body": normalize_original(body_original),
        }
        cats = post.get("categories") or [0]
        cat = str(cats[0]) if cats else "general"
        for ch in chunk_article(
            wp_id, normalize_original(title), cat, post.get("date", ""), parsed["blocks"]
        ):
            ch["title"] = normalize_original(title)
            ch["content_normalized"] = normalize_search(ch["content"])
            ch["published_at"] = post.get("date", "")
            ch["category"] = cat
            ch["category_id"] = cats[0] if cats else 0
            chunks.append(ch)
    vectors = {ch["id"]: embedder.embed(ch["embed_text"]) for ch in chunks}
    for ch in chunks:
        ch["embedding_model"] = embedder.model_id
    backend.index(chunks, vectors)
    by_id = {ch["id"]: ch for ch in chunks}
    return backend, by_id, articles
