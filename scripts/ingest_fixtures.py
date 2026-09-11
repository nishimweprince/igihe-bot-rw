"""Ingest bundled fixtures; print coverage + failure report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from igihe_assistant.extraction.parser import extract, rendered_text
from igihe_assistant.ingestion.runner import ingest_posts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default="tests/fixtures/wp")
    ap.add_argument("--out", default="data")
    args = ap.parse_args()
    sample = Path(args.sample)
    out = Path(args.out)
    posts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(sample.glob("*.json"))]
    result = ingest_posts(posts, out)
    ok = quarantined = 0
    for post in posts:
        parsed = extract(rendered_text(post))
        if parsed["status"] == "ok":
            ok += 1
        else:
            quarantined += 1
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "fetched": result.fetched,
                "changed": result.changed,
                "unchanged": result.unchanged,
                "failed": result.failed,
                "extract_ok": ok,
                "quarantined": quarantined,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
