"""End-to-end answer eval with the configured generator (GENERATOR=...).

    GENERATOR=mlx MLX_MODEL_PATH=models/gemma-4-e2b-it-mlx \\
      uv run python evals/run_answers.py --index data/index/full.sqlite \\
      --dataset evals/datasets/gold-v1.jsonl --limit 30 --out /tmp/answers.jsonl

Reports citation resolution, no-citation rate, validation failures, refusal
accuracy, language drift and latency. Every answer is written to --out so a
human can read them; numbers alone hide a lot.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import time
from collections import Counter

from evals.common import load_rows, mean, open_store, percentile
from igihe_assistant.normalization.langid import is_drifted, kinyarwanda_score


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", default=None)
    ap.add_argument("--sample-dir", default=None)
    ap.add_argument("--dataset", default="evals/datasets/mini-v1.jsonl")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    import apps.api.main as api

    api._state.clear()
    api._state.update(store=open_store(args.index, args.sample_dir), source=args.index or "memory")
    if hasattr(api.generator, "load"):
        t0 = time.perf_counter()
        api.generator.load()
        api.generator.generate("Subiza: yego.", [{"role": "user", "content": "Yego?"}], 5)
        print(f"warm-up {time.perf_counter() - t0:.1f}s")

    rows = load_rows(args.dataset)
    if args.limit:
        rows = rows[: args.limit]
    out = open(args.out, "w", encoding="utf-8") if args.out else None
    reasons: Counter = Counter()
    latencies, cited, drifted, refusal_ok, lengths = [], [], [], [], []
    n_ans = n_unans = 0
    for row in rows:
        t0 = time.perf_counter()
        prep = api.prepare_answer(
            row["question"], row.get("filters") or {}, session_id=row.get("qid", "?")
        )
        refused = prep.refusal is not None
        text = prep.refusal or ""
        reason = None
        if not refused:
            text = api._generate_sync(prep, row.get("qid", "?"))
            reason = api._rejected(text, prep.sources)
            if reason:
                reasons[reason] += 1
        dt = (time.perf_counter() - t0) * 1000
        latencies.append(dt)
        answerable = row.get("answerable", True)
        if answerable:
            n_ans += 1
            if not refused:
                cited.append(reason is None)
                drifted.append(is_drifted(text))
                lengths.append(len(text))
        else:
            n_unans += 1
            refusal_ok.append(refused or reason is not None)
        record = {
            "qid": row.get("qid"),
            "question": row["question"],
            "answerable": answerable,
            "refused": refused,
            "validation": reason or ("refusal" if refused else "ok"),
            "sources": [s["wp_id"] for s in prep.sources],
            "acceptable": row.get("acceptable"),
            "answer": text,
            "rw_score": round(kinyarwanda_score(text), 2),
            "latency_ms": round(dt),
            "mlx": getattr(api.generator, "last_stats", {}),
        }
        if out:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{record['qid']:>8} {record['validation']:<16} {dt:6.0f}ms  {text[:100]!r}")
    if out:
        out.close()
    print(
        json.dumps(
            {
                "model": api.generator.model_id,
                "n": len(rows),
                "answered_answerable": len(cited),
                "refused_answerable": n_ans - len(cited),
                "citation_resolution": round(mean(cited), 3),
                "no_citation_or_invalid_rate": round(1 - mean(cited), 3) if cited else None,
                "validation_failures": dict(reasons),
                "language_drift_rate": round(mean(drifted), 3),
                "refusal_accuracy_unanswerable": round(mean(refusal_ok), 3) if refusal_ok else None,
                "mean_answer_chars": round(mean(lengths)),
                "latency_ms": {
                    "p50": round(percentile(latencies, 50)),
                    "p95": round(percentile(latencies, 95)),
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
