"""First-token/total latency probe at fixed concurrency (SSE timing).

Usage:
    uv run python scripts/latency_probe.py --base http://localhost:8001 \
        --concurrency 1 --repeats 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx


async def one(client: httpx.AsyncClient, base: str, question: str) -> tuple[float, float]:
    t0 = time.monotonic()
    first = total = -1.0
    pending: str | None = None
    async with client.stream(
        "POST",
        f"{base}/v1/chat",
        json={"session_id": "latency", "message": question},
    ) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if line.startswith("event: "):
                pending = line[len("event: ") :]
                if pending == "token" and first < 0:
                    first = time.monotonic() - t0
                elif pending == "done":
                    total = time.monotonic() - t0
    if first < 0 or total < 0:
        raise RuntimeError("incomplete SSE stream (no token/done events)")
    return first, total


async def main_async(base: str, question: str, concurrency: int, repeats: int) -> None:
    firsts: list[float] = []
    totals: list[float] = []
    async with httpx.AsyncClient(timeout=600) as client:
        for _ in range(repeats):
            results = await asyncio.gather(
                *[one(client, base, question) for _ in range(concurrency)]
            )
            for first, total in results:
                firsts.append(first)
                totals.append(total)
    print(
        json.dumps(
            {
                "question": question,
                "concurrency": concurrency,
                "repeats": repeats,
                "first_token_s": {
                    "median": round(statistics.median(firsts), 1),
                    "max": round(max(firsts), 1),
                },
                "total_s": {
                    "median": round(statistics.median(totals), 1),
                    "max": round(max(totals), 1),
                },
            },
            indent=2,
        )
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    ap.add_argument("--question", default="Amazi meza i Kigali?")
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--repeats", type=int, default=2)
    args = ap.parse_args()
    asyncio.run(main_async(args.base, args.question, args.concurrency, args.repeats))


if __name__ == "__main__":
    main()
