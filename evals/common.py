"""Shared eval helpers: dataset rows, store loading, ranking metrics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from igihe_assistant.pipeline import build_index  # noqa: E402
from igihe_assistant.retrieval.store import IndexStore  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "wp"


def load_rows(path: str | Path) -> list[dict]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            if row.get("question", "").strip():
                rows.append(row)
    return rows


def open_store(index_path: str | None, sample_dir: str | None = None) -> IndexStore:
    """Persistent index when given, else an in-memory build (sample or fixtures)."""
    if index_path:
        return IndexStore(index_path)
    posts = []
    if sample_dir:
        for p in sorted(Path(sample_dir).glob("page-*.json")):
            posts.extend(json.loads(p.read_text(encoding="utf-8")))
    if not posts:
        posts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES.glob("*.json"))]
    return build_index(posts)


def recall_at(ranked: list[int], acceptable: set[int], k: int) -> float:
    return 1.0 if any(w in acceptable for w in ranked[:k]) else 0.0


def reciprocal_rank(ranked: list[int], acceptable: set[int]) -> float:
    for i, w in enumerate(ranked, start=1):
        if w in acceptable:
            return 1.0 / i
    return 0.0


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, max(0, round((p / 100) * (len(s) - 1))))
    return s[idx]


def mean(values) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
