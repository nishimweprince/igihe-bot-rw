"""Candidate ranking: tiered trigram BM25 x coverage x recency, grouped."""

from __future__ import annotations

from dataclasses import dataclass

from ..index.builder import published_day
from .query import Query, coverage
from .store import Hit, IndexStore


def rrf_merge(rankings: list[list], k: int = 60) -> list[tuple]:
    scores: dict = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def group_near_duplicates(chunk_ids: list, by_id: dict) -> list:
    """Keep best chunk per article, then collapse repeated story titles."""
    best_per_article: dict[int, object] = {}
    for cid in chunk_ids:
        wp = by_id[cid]["wp_id"]
        if wp not in best_per_article:
            best_per_article[wp] = cid
    ordered = [c for c in chunk_ids if best_per_article.get(by_id[c]["wp_id"]) == c]
    seen_titles: set[str] = set()
    out = []
    for cid in ordered:
        title_key = (by_id[cid].get("title") or "").strip().lower()[:40]
        if title_key and title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        out.append(cid)
    return out


@dataclass
class Candidate:
    cid: int
    wp_id: int
    score: float
    bm25: float
    coverage: float
    published_day: int
    chunk: dict


def evidence_coverage(cands: list[Candidate], q: Query, top_n: int = 3) -> float:
    """Query coverage by the evidence set as a whole (multi-topic questions
    are answered from several articles, none of which covers every term)."""
    if not cands or not q.groups:
        return 0.0
    text = "\n".join(f"{c.chunk['title']}\n{c.chunk['content']}" for c in cands[:top_n])
    return coverage(text, q.groups)


def recency_multiplier(age_days: float, weight: float, half_life_days: float) -> float:
    if weight <= 0 or half_life_days <= 0:
        return 1.0
    return 1.0 + weight * 0.5 ** (max(age_days, 0.0) / half_life_days)


def index_now_day(store: IndexStore) -> int:
    """Anchor "now" to the newest article, not the wall clock."""
    newest = store.meta().get("max_published_at") or store.stats()["max_published_at"]
    return published_day(newest) if newest else 0


def _with_window(filters: dict | None, after_day: int) -> dict:
    from datetime import date, timedelta

    cutoff = (date(1970, 1, 1) + timedelta(days=after_day)).isoformat()
    out = dict(filters or {})
    if not out.get("published_after") or str(out["published_after"]) < cutoff:
        out["published_after"] = cutoff
    return out


def retrieve(
    q: Query,
    store: IndexStore,
    filters: dict | None = None,
    *,
    candidates_n: int = 200,
    final_n: int = 6,
    recency_weight: float = 0.3,
    half_life_days: float = 365.0,
    recency_window_days: int = 180,
    min_strict_hits: int = 10,
    min_window_hits: int = 3,
    now_day: int | None = None,
) -> list[Candidate]:
    """Ranked, article-deduplicated candidates for a question."""
    now = index_now_day(store) if now_day is None else now_day
    if q.browse:
        hits = store.newest(final_n * 3, filters)
        return _finish(hits, store, q, now, 0.0, 1.0, final_n)

    weight, half_life = recency_weight, half_life_days
    if q.recency:
        weight, half_life = 1.0, 30.0
        windowed = _with_window(filters, now - recency_window_days)
        hits = _tiered(q, store, windowed, candidates_n, min_strict_hits)
        if len(hits) < min_window_hits:
            hits = _tiered(q, store, filters, candidates_n, min_strict_hits)
    else:
        hits = _tiered(q, store, filters, candidates_n, min_strict_hits)
    return _finish(hits, store, q, now, weight, half_life, final_n)


def _tiered(q: Query, store: IndexStore, filters, n: int, min_strict: int) -> list[Hit]:
    if not q.groups:
        return []
    hits = store.lexical(q.match_strict, n, filters)
    if len(hits) < min_strict and len(q.groups) > 1:
        seen = {h.cid for h in hits}
        hits += [h for h in store.lexical(q.match_loose, n, filters) if h.cid not in seen]
    return hits


def _finish(hits, store, q, now, weight, half_life, final_n) -> list[Candidate]:
    if not hits:
        return []
    chunks = store.get_chunks([h.cid for h in hits])
    cands: list[Candidate] = []
    for h in hits:
        ch = chunks.get(h.cid)
        if not ch:
            continue
        cov = coverage(f"{ch['title']}\n{ch['content']}", q.groups) if q.groups else 1.0
        base = max(-h.bm25, 1e-6) if not q.browse else 1.0
        score = (
            base * (0.5 + 0.5 * cov) * recency_multiplier(now - h.published_day, weight, half_life)
        )
        cands.append(Candidate(h.cid, h.wp_id, score, h.bm25, cov, h.published_day, ch))
    if q.browse:
        cands.sort(key=lambda c: c.published_day, reverse=True)
    else:
        cands.sort(key=lambda c: c.score, reverse=True)
    by_id = {c.cid: c.chunk for c in cands}
    keep = group_near_duplicates([c.cid for c in cands], by_id)[:final_n]
    order = {cid: i for i, cid in enumerate(keep)}
    return sorted((c for c in cands if c.cid in order), key=lambda c: order[c.cid])
