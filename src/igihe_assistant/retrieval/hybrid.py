"""Hybrid retrieval: dual top-N, RRF merge, near-dup grouping."""

from __future__ import annotations


def rrf_merge(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def group_near_duplicates(chunk_ids: list[str], by_id: dict[str, dict]) -> list[str]:
    """Keep best chunk per article, then collapse repeated story titles."""
    best_per_article: dict[int, str] = {}
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


def retrieve(
    query: str,
    query_vec: list[float],
    backend,
    embedder=None,
    top_lex: int = 40,
    top_dense: int = 40,
    final_n: int = 6,
    filters: dict | None = None,
    candidates: str = "hybrid",
) -> list[str]:
    lex = [cid for cid, _ in backend.lexical(query, top_lex, filters)]
    den = [cid for cid, _ in backend.dense(query_vec, top_dense, filters)]
    if candidates == "lexical":
        # Demo tuning while dense vectors are unreviewed placeholders:
        # finalists must carry lexical support, ordered lexically with
        # dense rank as tiebreak only. Revisit after the embedding bake-off.
        den_rank = {cid: i + 1 for i, cid in enumerate(den)}
        merged = sorted(
            lex,
            key=lambda cid: (lex.index(cid), den_rank.get(cid, 10**6)),
        )
    else:
        merged = [cid for cid, _ in rrf_merge([lex, den])]
    grouped = group_near_duplicates(merged, backend.chunks)
    return grouped[:final_n]
