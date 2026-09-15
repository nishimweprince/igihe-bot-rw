"""Fixture pipeline: posts -> in-memory IndexStore (tests, evals, dev)."""

from __future__ import annotations

from .index.builder import bulk_build
from .retrieval.store import IndexStore


def build_index(posts: list[dict]) -> IndexStore:
    store = IndexStore.create(":memory:")
    bulk_build(store, posts)
    return store
