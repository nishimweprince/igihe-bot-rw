"""Generator contract + deterministic fake (plumbing, not quality)."""

from __future__ import annotations

from typing import Protocol

from ..prompting.builder import NO_EVIDENCE_RW


class Generator(Protocol):
    model_id: str

    def generate(self, prompt: str, sources: list[dict], max_tokens: int) -> str: ...


class FakeGenerator:
    model_id = "fake-gen-v1"

    def generate(self, prompt: str, sources: list[dict], max_tokens: int = 400) -> str:
        if not sources:
            return NO_EVIDENCE_RW
        lines = []
        for i, s in enumerate(sources[:2], start=1):
            snippet = s["content"][:140].replace("\n", " ")
            lines.append(f"{snippet} [{i}]")
        head = "Mu nkuru za IGIHE nabonye ko: "
        text = head + " ".join(lines)
        # Crude token cap by words.
        words = text.split()
        return " ".join(words[:max_tokens])
