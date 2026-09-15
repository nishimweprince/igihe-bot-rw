"""Retrieval-only eval: recall@k, MRR, refusal gate, latency. No LLM.

    uv run python evals/run_retrieval.py --dataset evals/datasets/mini-v1.jsonl
    uv run python evals/run_retrieval.py --index data/index/full.sqlite \\
        --dataset evals/datasets/gold-v1.jsonl
    uv run python evals/run_retrieval.py --index data/index/full.sqlite --self-retrieval 200

Almost every bad answer is a retrieval miss wearing a generation costume;
this separates the two. `--self-retrieval N` samples N articles and asks
whether each headline retrieves its own article (a sanity floor, not a gold
set).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import random
import time
from collections import defaultdict

from evals.common import load_rows, mean, open_store, percentile, recall_at, reciprocal_rank
from igihe_assistant.config import Settings
from igihe_assistant.retrieval.query import analyze
from igihe_assistant.retrieval.rank import evidence_coverage, retrieve
from igihe_assistant.retrieval.rerank import load_reranker, rerank


def run_rows(store, rows, settings: Settings, final_n: int = 10, reranker=None) -> dict:
    by_kind: dict[str, list[dict]] = defaultdict(list)
    by_lang: dict[str, list[dict]] = defaultdict(list)
    latencies: list[float] = []
    results = []
    for row in rows:
        q = analyze(row["question"])
        t0 = time.perf_counter()
        cands = retrieve(
            q, store, row.get("filters"), final_n=final_n,
            candidates_n=settings.candidates_n, recency_weight=settings.recency_weight,
            half_life_days=settings.recency_half_life_days,
            recency_window_days=settings.recency_window_days,
        )
        if reranker is not None:
            cands = rerank(row["question"], cands, reranker)
        latencies.append((time.perf_counter() - t0) * 1000)
        ranked = [c.wp_id for c in cands]
        acc = set(row.get("acceptable") or [])
        top_cov = evidence_coverage(cands, q)
        would_answer = bool(cands) and (q.browse or top_cov >= settings.min_coverage)
        res = {
            "qid": row.get("qid"), "answerable": row.get("answerable", True),
            "kind": row.get("kind", "?"), "lang": row.get("lang", "rw"),
            "ranked": ranked[:final_n], "would_answer": would_answer, "coverage": round(top_cov, 2),
            "r1": recall_at(ranked, acc, 1), "r5": recall_at(ranked, acc, 5),
            "r10": recall_at(ranked, acc, 10), "rr": reciprocal_rank(ranked, acc),
        }
        results.append(res)
        by_kind[res["kind"]].append(res)
        by_lang[res["lang"]].append(res)

    def summarize(rs: list[dict]) -> dict:
        ans = [r for r in rs if r["answerable"]]
        unans = [r for r in rs if not r["answerable"]]
        return {
            "n": len(rs),
            "recall@1": round(mean(r["r1"] for r in ans), 3),
            "recall@5": round(mean(r["r5"] for r in ans), 3),
            "recall@10": round(mean(r["r10"] for r in ans), 3),
            "mrr": round(mean(r["rr"] for r in ans), 3),
            "answer_rate_answerable": round(mean(r["would_answer"] for r in ans), 3),
            "refusal_rate_unanswerable": round(mean(not r["would_answer"] for r in unans), 3),
        }

    return {
        "overall": summarize(results),
        "by_kind": {k: summarize(v) for k, v in sorted(by_kind.items())},
        "by_lang": {k: summarize(v) for k, v in sorted(by_lang.items())},
        "latency_ms": {"p50": round(percentile(latencies, 50), 1),
                       "p95": round(percentile(latencies, 95), 1)},
        "rows": results,
    }


def self_retrieval_rows(store, n: int, seed: int = 7) -> list[dict]:
    conn = store.conn
    total = conn.execute("SELECT COUNT(*) FROM articles WHERE status='ok'").fetchone()[0]
    rng = random.Random(seed)
    offsets = sorted(rng.sample(range(total), min(n, total)))
    rows = []
    for off in offsets:
        r = conn.execute(
            "SELECT wp_id, title FROM articles WHERE status='ok' ORDER BY wp_id LIMIT 1 OFFSET ?",
            (off,),
        ).fetchone()
        rows.append({"qid": f"self-{r['wp_id']}", "question": r["title"], "answerable": True,
                     "kind": "self", "lang": "rw", "acceptable": [r["wp_id"]]})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", default=None, help="persistent index (default: fixtures in memory)")
    ap.add_argument("--sample-dir", default=None)
    ap.add_argument("--dataset", default=None)
    ap.add_argument("--self-retrieval", type=int, default=0, metavar="N")
    ap.add_argument("--out", default=None, help="write per-question rows as JSONL")
    ap.add_argument("--reranker", default=None, help="RERANKER_MODEL value for a bake-off")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if not args.dataset and not args.self_retrieval:
        args.dataset = "evals/datasets/mini-v1.jsonl"

    store = open_store(args.index, args.sample_dir)
    settings = Settings()
    rows = load_rows(args.dataset) if args.dataset else []
    if args.self_retrieval:
        rows += self_retrieval_rows(store, args.self_retrieval)
    reranker = None
    if args.reranker:
        settings.reranker_model = args.reranker
        reranker = load_reranker(settings)
    report = run_rows(store, rows, settings, reranker=reranker)
    per_row = report.pop("rows")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            for r in per_row:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if args.verbose:
        for r in per_row:
            flag = "" if (r["r10"] or not r["answerable"]) else "  <-- MISS"
            print(f"{r['qid']:>10} r10={r['r10']:.0f} cov={r['coverage']:.2f} "
                  f"answer={r['would_answer']} top={r['ranked'][:3]}{flag}")
    print(json.dumps({"index": args.index or "memory", "dataset": args.dataset,
                      "self_retrieval": args.self_retrieval,
                      "reranker": reranker.model_id if reranker else None, **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
