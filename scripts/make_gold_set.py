"""Draft a gold-set template: stratified article sample for human questions.

    uv run python scripts/make_gold_set.py --index data/index/full.sqlite --n 100 \\
        --out evals/datasets/gold-v1.template.jsonl [--draft-questions]

Each row carries the source article (title, url, date, lead) and an empty
`question` for a Kinyarwanda speaker to fill in. With --draft-questions the
configured generator proposes one question per article (marked draft=true)
for editing. Rows without a question are ignored by the eval runners, so a
half-filled file still runs. Ten blank `unanswerable` rows are appended.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from igihe_assistant.retrieval.store import IndexStore  # noqa: E402

# (share of sample, days-ago lower bound, days-ago upper bound) relative to newest article
STRATA = [(0.60, 0, 365), (0.25, 365, 365 * 8), (0.10, 365 * 8, 365 * 11), (0.05, 365 * 11, 10**6)]
KINDS = ("factual", "name", "date", "multi", "recency")


def sample_articles(store: IndexStore, n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    newest = date.fromisoformat(store.meta()["max_published_at"][:10])
    chosen: list[dict] = []
    cat_counts: Counter = Counter()
    for share, lo, hi in STRATA:
        want = max(1, round(n * share))
        after = (newest - timedelta(days=hi)).isoformat()
        before = (newest - timedelta(days=lo)).isoformat()
        rows = store.conn.execute(
            "SELECT wp_id, title, url, published_at, category_id, substr(body, 1, 400) AS lead "
            "FROM articles WHERE status='ok' AND published_at >= ? AND published_at <= ? "
            "AND length(body) > 400 ORDER BY random() LIMIT ?",
            (after, before, want * 6),
        ).fetchall()
        rows = [dict(r) for r in rows]
        rng.shuffle(rows)
        picked = 0
        for r in rows:  # spread across categories: at most n/8 per category
            if cat_counts[r["category_id"]] >= max(2, n // 8):
                continue
            cat_counts[r["category_id"]] += 1
            chosen.append(r)
            picked += 1
            if picked >= want:
                break
    return chosen[:n]


def draft_question(generator, art: dict) -> str:
    system = (
        "Uri umwanditsi w'ibibazo. Andika ikibazo kimwe gusa mu Kinyarwanda, "
        "kigufi, umuntu yabaza kugira ngo asubizwe n'iyi nkuru. Ntusubize; "
        "andika ikibazo gusa."
    )
    user = f"Inkuru: {art['title']}\n{art['lead']}\n\nIkibazo:"
    try:
        return (
            generator.generate(system, [{"role": "user", "content": user}], 40)
            .strip()
            .split("\n")[0]
        )
    except Exception as exc:  # noqa: BLE001
        return f"(draft failed: {exc})"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--draft-questions", action="store_true")
    args = ap.parse_args()

    store = IndexStore(args.index)
    arts = sample_articles(store, args.n, args.seed)
    generator = None
    if args.draft_questions:
        from igihe_assistant.config import Settings
        from igihe_assistant.generation.factory import build_generator

        generator = build_generator(Settings())
        if hasattr(generator, "load"):
            generator.load()
    rows = []
    for i, art in enumerate(arts, start=1):
        row = {
            "qid": f"g{i:03d}",
            "question": "",
            "lang": "rw",
            "kind": KINDS[i % len(KINDS)],
            "answerable": True,
            "acceptable": [art["wp_id"]],
            "recency_cue": False,
            "source_title": art["title"],
            "source_url": art["url"],
            "published_at": art["published_at"],
            "lead": art["lead"],
            "notes": "",
        }
        if generator is not None:
            row["question"] = draft_question(generator, art)
            row["draft"] = True
            print(f"{row['qid']} {row['question']!r}", flush=True)
        rows.append(row)
    for j in range(1, 11):
        rows.append(
            {
                "qid": f"u{j:02d}",
                "question": "",
                "lang": "rw",
                "kind": "unanswerable",
                "answerable": False,
                "acceptable": [],
                "recency_cue": False,
                "notes": "write a plausible question IGIHE would not have covered",
            }
        )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
