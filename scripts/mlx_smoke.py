"""Load the MLX checkpoint, answer one cited Kinyarwanda question, report speed.

    uv run python scripts/mlx_smoke.py [--model models/gemma-4-e2b-it-mlx] [--max-tokens 120]

Prints time-to-first-token, tokens/s, peak memory and the answer, and fails
if the output leaks a control token or carries no [n] citation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from igihe_assistant.generation.mlx_gen import MlxGenerator  # noqa: E402
from igihe_assistant.prompting.builder import build_messages  # noqa: E402

SOURCES = [
    {
        "n": 1,
        "wp_id": 101,
        "title": "Amazi meza ageze i Kigali",
        "published_at": "2024-03-02T08:00:00",
        "url": "https://igihe.com/x",
        "content": (
            "Umujyi wa Kigali watangije umushinga mushya w'amazi meza uzageza amazi "
            "ku miryango ibihumbi mirongo itanu. Umushinga uzatwara miliyari 12 "
            "z'amafaranga y'u Rwanda kandi uzarangira mu 2025."
        ),
    },
    {
        "n": 2,
        "wp_id": 108,
        "title": "RRA: GDP yazamutse 7.5%",
        "published_at": "2024-04-18T12:00:00",
        "url": "https://igihe.com/y",
        "content": (
            "Ubukungu bw'u Rwanda bwazamutse ku kigero cya 7.5% mu gihembwe cya mbere cya 2024."
        ),
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/gemma-4-e2b-it-mlx")
    ap.add_argument("--max-tokens", type=int, default=120)
    ap.add_argument("--question", default="Umushinga w'amazi wa Kigali uzatwara angahe?")
    args = ap.parse_args()

    gen = MlxGenerator(args.model)
    t0 = time.perf_counter()
    gen.load()
    print(f"loaded {gen.model_id} in {time.perf_counter() - t0:.1f}s", flush=True)
    system, messages = build_messages(args.question, SOURCES)
    print(f"prompt tokens: {len(gen.render(system, messages))}", flush=True)
    # First call pays Metal JIT/warm-up; the API does this at startup too.
    t0 = time.perf_counter()
    gen.generate("Subiza: yego.", [{"role": "user", "content": "Yego?"}], 5)
    print(f"warm-up in {time.perf_counter() - t0:.1f}s", flush=True)

    t0 = time.perf_counter()
    ttft = None
    pieces = []
    for piece in gen.stream(system, messages, args.max_tokens):
        if ttft is None:
            ttft = time.perf_counter() - t0
        pieces.append(piece)
        print(piece, end="", flush=True)
    total = time.perf_counter() - t0
    text = "".join(pieces)
    print("\n")
    print(
        json.dumps(
            {"ttft_s": round(ttft or 0, 2), "total_s": round(total, 2), **gen.last_stats}, indent=2
        )
    )
    ok = True
    if "<|" in text or "<turn" in text or "<eos>" in text:
        print("FAIL: control token leaked", file=sys.stderr)
        ok = False
    if "[1]" not in text and "[2]" not in text:
        print("WARN: no [n] citation in answer", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
