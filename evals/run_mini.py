"""Mini eval runner: Recall@5/10, MRR, citation resolution, refusal."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from igihe_assistant.embeddings.embedder import FakeHashEmbedder
from igihe_assistant.generation.generator import FakeGenerator
from igihe_assistant.generation.validator import validate
from igihe_assistant.normalization.normalize import normalize_search
from igihe_assistant.pipeline import build_index
from igihe_assistant.prompting.builder import NO_EVIDENCE_RW, build_prompt
from igihe_assistant.retrieval.hybrid import retrieve


def recall_at(ranked: list[int], acceptable: set[int], k: int) -> float:
    return 1.0 if any(w in acceptable for w in ranked[:k]) else 0.0


def rr(ranked: list[int], acceptable: set[int]) -> float:
    for i, w in enumerate(ranked, start=1):
        if w in acceptable:
            return 1.0 / i
    return 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="evals/datasets/mini-v1.jsonl")
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    posts = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((root / "tests" / "fixtures" / "wp").glob("*.json"))
    ]
    embedder = FakeHashEmbedder()
    gen = FakeGenerator()
    backend, by_id, articles = build_index(posts, embedder)
    rows = [
        json.loads(line) for line in Path(args.dataset).read_text().splitlines() if line.strip()
    ]
    r5 = r10 = mrr = cite_ok = refuse_ok = n_cite = n_ref = 0
    for row in rows:
        filt = row.get("filters")
        ranked_ids = retrieve(
            normalize_search(row["question"]),
            embedder.embed(normalize_search(row["question"])),
            backend,
            final_n=10,
            filters=filt,
        )
        ranked_wp = [by_id[c]["wp_id"] for c in ranked_ids]
        acc = set(row["acceptable"])
        if row["answerable"]:
            r5 += recall_at(ranked_wp, acc, 5)
            r10 += recall_at(ranked_wp, acc, 10)
            mrr += rr(ranked_wp, acc)
            sources = [
                {
                    "n": i + 1,
                    "wp_id": by_id[c]["wp_id"],
                    "title": articles[by_id[c]["wp_id"]]["title"],
                    "published_at": articles[by_id[c]["wp_id"]]["published_at"],
                    "url": articles[by_id[c]["wp_id"]]["url"],
                    "content": by_id[c]["content"],
                }
                for i, c in enumerate(ranked_ids[:6])
            ]
            text = (
                gen.generate(build_prompt(row["question"], sources), sources, 400)
                if sources
                else NO_EVIDENCE_RW
            )
            ok, _ = validate(text, sources)
            cite_ok += bool(ok)
            n_cite += 1
        else:
            n_ref += 1
            if not ranked_wp or True:
                # Refusal correctness: unanswerable probe through the real path.
                from apps.api.main import answer_question

                text, sources = answer_question(row["question"], filt or {})
                # For the fixture slice, refusal means empty sources or no-evidence text.
                if not sources or text == NO_EVIDENCE_RW:
                    refuse_ok += 1
    n_ans = sum(1 for r in rows if r["answerable"])
    print(
        json.dumps(
            {
                "dataset": "mini-v1",
                "n": len(rows),
                "recall@5": round(r5 / max(n_ans, 1), 3),
                "recall@10": round(r10 / max(n_ans, 1), 3),
                "mrr": round(mrr / max(n_ans, 1), 3),
                "citation_resolution": round(cite_ok / max(n_cite, 1), 3),
                "refusal_accuracy": round(refuse_ok / max(n_ref, 1), 3),
                "note": "fixture-slice baseline, not a release gate",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
