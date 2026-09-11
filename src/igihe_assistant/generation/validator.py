"""Server-owned citation validation (never trust model output)."""

from __future__ import annotations

import re

CITE = re.compile(r"\[(\d+)\]")
ECHO_RECORD = re.compile(r"id=\d+")


def validate(answer: str, sources: list[dict]) -> tuple[bool, str]:
    """Return (ok, reason). Invalid citations must block authoritative send."""
    from ..prompting.builder import ECHO_PHRASES

    if not answer or not answer.strip():
        return False, "empty"
    lowered = answer.lower()
    if ECHO_RECORD.search(answer) or any(p.lower() in lowered for p in ECHO_PHRASES):
        # Model echoed the prompt template instead of answering.
        return False, "evidence-echo"
    nums = [int(n) for n in CITE.findall(answer)]
    if nums and max(nums) > len(sources):
        return False, "unknown-citation"
    urls = {s["url"] for s in sources}
    for token in re.findall(r"https?://\S+", answer):
        if token.rstrip(".,)") not in urls:
            return False, "unindexed-url"
    return True, "ok"
