"""Embedder adapter contract (fake default; BGE-M3/E5 later)."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol


class Embedder(Protocol):
    model_id: str
    revision: str
    dim: int

    def embed(self, text: str) -> list[float]: ...

    def token_count(self, text: str) -> int: ...


class FakeHashEmbedder:
    """Deterministic char-hash vector; proves plumbing, not quality."""

    model_id = "fake-hash-v1"
    revision = "v1"
    dim = 64

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for i, ch in enumerate(text.lower()):
            h = int(hashlib.sha256(f"{i % 8}|{ch}".encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def token_count(self, text: str) -> int:
        return len(text.split())
