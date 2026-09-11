"""Baseline retrieval/answer probe on the live sample (not a release gate).

Loads data/live-sample/pages, swaps the live index into the real API
answer path, and reports self-retrieval recall, citation resolution,
and refusal accuracy.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import apps.api.main as api  # noqa: E402
from igihe_assistant.embeddings.embedder import FakeHashEmbedder  # noqa: E402
from igihe_assistant.normalization.normalize import content_terms  # noqa: E402
from igihe_assistant.pipeline import build_index  # noqa: E402
from igihe_assistant.retrieval.hybrid import retrieve  # noqa: E402

UNANSWERABLE = [
    "Ni iki cyabaye ku mubumbe Mars ejo?",
    "Ninde watwaye igikombe cy'isi cya 2030?",
    "xyzzy blorpt quux nabi?",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default="data/live-sample/pages")
    ap.add_argument("--k", type=int, default=20)
    args = ap.parse_args()

    posts = []
    for path in sorted(Path(args.sample).glob("page-*.json")):
        posts.extend(json.loads(path.read_text(encoding="utf-8")))
    embedder = FakeHashEmbedder()
    backend, by_id, articles = build_index(posts, embedder)
    api._state.update(backend=backend, by_id=by_id, articles=articles)

    ids = sorted(articles)
    chosen = [ids[i * len(ids) // args.k] for i in range(args.k)]
    hits5 = hits10 = rr = 0.0
    for wp_id in chosen:
        title = articles[wp_id]["title"]
        terms = content_terms(title)
        if not terms:
            continue
        q = " ".join(terms[:8])
        ranked = retrieve(
            q, embedder.embed(q), backend, final_n=10, filters=None
        )
        ranked_wp = [by_id[c]["wp_id"] for c in ranked]
        if wp_id in ranked_wp[:5]:
            hits5 += 1
        if wp_id in ranked_wp[:10]:
            hits10 += 1
            rr += 1.0 / (ranked_wp.index(wp_id) + 1)
    n = len(chosen)
    cite_ok = cite_n = 0
    for wp_id in chosen[:5]:
        title = articles[wp_id]["title"]
        terms = content_terms(title)
        text, sources = api.answer_question(" ".join(terms[:8]), {})
        if sources:
            from igihe_assistant.generation.validator import validate

            cite_n += 1
            cite_ok += validate(text, sources)[0]
    refusals = sum(
        1 for q in UNANSWERABLE if api.answer_question(q, {})[1] == []
    )
    print(
        json.dumps(
            {
                "articles": len(articles),
                "self_recall@5": round(hits5 / n, 3),
                "self_recall@10": round(hits10 / n, 3),
                "self_mrr": round(rr / n, 3),
                "citation_resolution": round(cite_ok / max(cite_n, 1), 3),
                "refusal_accuracy": round(refusals / len(UNANSWERABLE), 3),
                "note": "live-sample baseline, not a release gate",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
