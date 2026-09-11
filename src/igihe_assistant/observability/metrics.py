"""Privacy-preserving counters (no raw text logged by default)."""

from __future__ import annotations

from collections import Counter

counters: Counter[str] = Counter()


def incr(name: str, n: int = 1) -> None:
    counters[name] += n


def snapshot() -> dict:
    return dict(counters)
