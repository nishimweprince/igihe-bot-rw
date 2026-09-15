"""Generator contract + deterministic fake (plumbing, not quality)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from ..prompting.builder import NO_EVIDENCE_RW, Message, parse_evidence_block


class Generator(Protocol):
    model_id: str

    def stream(self, system: str, messages: list[Message], max_tokens: int) -> Iterator[str]:
        """Yield answer text pieces in order (tokens, words or sentences)."""

    def generate(self, system: str, messages: list[Message], max_tokens: int) -> str:
        """Full answer; equivalent to ''.join(stream(...))."""


class FakeGenerator:
    model_id = "fake-gen-v1"

    def generate(self, system: str, messages: list[Message], max_tokens: int = 400) -> str:
        sources = parse_evidence_block(messages[-1]["content"]) if messages else []
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

    def stream(self, system: str, messages: list[Message], max_tokens: int = 400) -> Iterator[str]:
        # Word-sized pieces so the SSE bridge and incremental validation are
        # exercised the same way a real model exercises them.
        text = self.generate(system, messages, max_tokens)
        words = text.split(" ")
        for i, w in enumerate(words):
            yield w if i == len(words) - 1 else w + " "
