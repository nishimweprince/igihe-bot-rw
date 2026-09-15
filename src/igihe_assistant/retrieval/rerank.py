"""Optional neural reranker over the top lexical candidates (flag-gated).

Off by default (`RERANKER_MODEL=""`). On this 8 GB machine a torch
cross-encoder next to the 3.3 GB MLX model is tight, so a reranker ships
only after `evals/run_retrieval.py --reranker` shows a real recall@10 win
(the plan's bar: +5 points on the gold set).
"""

from __future__ import annotations

from typing import Protocol

from .rank import Candidate, rrf_merge


class Reranker(Protocol):
    model_id: str

    def score(self, query: str, passages: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """sentence-transformers CrossEncoder on CPU (lazy import, lazy load)."""

    def __init__(self, model_name: str, max_length: int = 384, batch_size: int = 16):
        self.model_id = f"cross-encoder:{model_name}"
        self._name = model_name
        self._max_length = max_length
        self._batch = batch_size
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as e:
                raise RuntimeError("install with `uv sync --extra rerank`") from e
            self._model = CrossEncoder(self._name, max_length=self._max_length, device="cpu")
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        model = self._load()
        return [
            float(s) for s in model.predict([(query, p) for p in passages], batch_size=self._batch)
        ]


class LlmPointwiseReranker:
    """Yego/oya relevance judgement from the already-loaded MLX generator.

    Zero extra memory; costs one short generation per candidate, so keep the
    candidate count small (top 10)."""

    def __init__(self, generator):
        self.model_id = f"llm-pointwise:{generator.model_id}"
        self._gen = generator

    def score(self, query: str, passages: list[str]) -> list[float]:
        system = "Subiza gusa 'yego' cyangwa 'oya'."
        out = []
        for p in passages:
            user = f"Inkuru: {p[:600]}\n\nIkibazo: {query}\nIyi nkuru isubiza iki kibazo?"
            try:
                text = self._gen.generate(system, [{"role": "user", "content": user}], 3).lower()
            except Exception:  # noqa: BLE001
                text = ""
            out.append(1.0 if text.startswith("yego") else 0.0)
        return out


def load_reranker(settings, generator=None):
    name = (getattr(settings, "reranker_model", "") or "").strip()
    if not name:
        return None
    if name == "llm-pointwise":
        if generator is None:
            raise ValueError("llm-pointwise reranker needs the generator")
        return LlmPointwiseReranker(generator)
    return CrossEncoderReranker(name)


def rerank(
    query: str, cands: list[Candidate], reranker: Reranker, top_k: int = 50
) -> list[Candidate]:
    """Blend reranker order with lexical order via RRF so a weak reranker
    cannot fully destroy the lexical prior."""
    head, tail = cands[:top_k], cands[top_k:]
    if not head:
        return cands
    scores = reranker.score(query, [f"{c.chunk['title']}\n{c.chunk['content']}" for c in head])
    lex_order = [c.cid for c in head]
    rr_order = [c.cid for c, _ in sorted(zip(head, scores, strict=True), key=lambda x: -x[1])]
    merged = [cid for cid, _ in rrf_merge([lex_order, rr_order])]
    by_cid = {c.cid: c for c in head}
    return [by_cid[cid] for cid in merged] + tail
