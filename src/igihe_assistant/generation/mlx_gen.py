"""MLX-backed generator for the local ALTA checkpoint (Apple Silicon).

Prompt format mirrors the `alta-models-sft` reference exactly: single-turn
ChatML (`<|im_start|>system/user/assistant`) with `<|im_end|>` as the stop.
Sampling defaults (temp 0.5, top_k 40, top_p 0.85, repetition penalty 1.05)
are ALTAChat's defaults.
"""

from __future__ import annotations

import threading
from pathlib import Path

IM_START = "<|im_start|>"
IM_END = "<|im_end|>"


def render_alta_chatml(system: str, user: str) -> str:
    """Single-turn ChatML prompt with the assistant generation header."""
    return (
        f"{IM_START}system\n{system}{IM_END}\n"
        f"{IM_START}user\n{user}{IM_END}\n"
        f"{IM_START}assistant\n"
    )


def strip_alta_stop(text: str) -> str:
    """Cut everything from the assistant stop token; the MLX tokenizer's
    eos set only contains `<|eos|>`, so generation does not stop on its own."""
    cut = text.find(IM_END)
    if cut != -1:
        text = text[:cut]
    text = text.strip()
    if text.endswith("Igisubizo:"):
        text = text[: -len("Igisubizo:")].strip()
    return text


class MlxGenerator:
    """Local MLX checkpoint with the fake-compatible contract.

    Weights load lazily on first `generate` (thread-safe) so importing the
    API never pays the ~672 MB load; mlx-lm itself is imported lazily too so
    this module imports cleanly where mlx-lm isn't installed.
    """

    def __init__(
        self,
        model_path: str,
        temperature: float = 0.5,
        top_p: float = 0.85,
        top_k: int = 40,
        repetition_penalty: float = 1.05,
    ):
        if not Path(model_path).is_dir():
            raise FileNotFoundError(f"MLX model directory not found: {model_path}")
        self._model_path = model_path
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._repetition_penalty = repetition_penalty
        self._lock = threading.Lock()
        self._loaded = None

    @property
    def model_id(self) -> str:
        return f"mlx:{Path(self._model_path).name}"

    def _ensure_loaded(self):
        if self._loaded is None:
            with self._lock:
                if self._loaded is None:
                    try:
                        from mlx_lm.utils import load as mlx_load
                    except ImportError as e:
                        raise RuntimeError(
                            "mlx-lm is not installed; use the project .venv"
                        ) from e
                    try:
                        self._loaded = mlx_load(self._model_path)
                    except Exception as e:
                        raise RuntimeError(
                            f"could not load MLX model at {self._model_path}: {e}"
                        ) from e
        return self._loaded

    def generate(self, prompt: str, sources: list[dict], max_tokens: int = 400) -> str:
        from mlx_lm import generate as mlx_generate
        from mlx_lm.sample_utils import make_logits_processors, make_sampler

        from ..prompting.builder import build_messages

        head, _, tail = prompt.rpartition("Igisubizo:")
        question = head.rsplit("Ikibazo:", 1)[-1].strip()
        system, user = build_messages(question, sources)
        if tail.strip():
            user += "\n" + tail.strip()
        chat_prompt = render_alta_chatml(system, user)

        model, tokenizer = self._ensure_loaded()
        text = mlx_generate(
            model,
            tokenizer,
            prompt=chat_prompt,
            max_tokens=max_tokens,
            sampler=make_sampler(self._temperature, self._top_p, top_k=self._top_k),
            logits_processors=make_logits_processors(
                repetition_penalty=self._repetition_penalty,
                repetition_context_size=64,
            ),
        )
        text = strip_alta_stop(text)
        if not text:
            raise RuntimeError("mlx model returned an empty response")
        return text
