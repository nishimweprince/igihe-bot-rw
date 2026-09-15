"""MLX-backed generator for local Gemma checkpoints (Apple Silicon).

The prompt goes through the checkpoint's own chat template (Gemma 4 has a
real `system` role), and tokens are produced with `mlx_lm.stream_generate`
so the API can forward them as they arrive. MLX is single-stream: a lock
serialises generations, and `MAX_CONCURRENT_GENERATIONS` should stay at 1.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Iterator
from pathlib import Path

from ..prompting.builder import Message

log = logging.getLogger("igihe.mlx")

# Gemma 4 control tokens that must never reach the client.
_CONTROL = re.compile(r"<\|channel>.*?<channel\|>|<turn\|>|<\|turn>|<eos>", re.S)
STOP_TOKEN_TEXT = "<turn|>"
# Gemma 4 opens a hidden reasoning block with this token even when thinking
# is not enabled in the template. Banning it at the logits keeps the small
# model answering directly (its English "thoughts" would otherwise eat the
# token budget and leak into the stream).
BANNED_TOKEN_TEXTS = ("<|channel>",)


def strip_control(text: str) -> str:
    cut = text.find(STOP_TOKEN_TEXT)
    if cut != -1:
        text = text[:cut]
    return _CONTROL.sub("", text).strip()


class MlxGenerator:
    def __init__(
        self,
        model_path: str,
        temperature: float = 0.4,
        top_p: float = 0.9,
        top_k: int = 64,
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
        self._banned: list[int] = []
        self.last_stats: dict = {}

    @property
    def model_id(self) -> str:
        return f"mlx:{Path(self._model_path).name}"

    def load(self):
        """Load weights (idempotent, thread-safe). Called eagerly at startup."""
        if self._loaded is None:
            with self._lock:
                if self._loaded is None:
                    try:
                        from mlx_lm import load as mlx_load
                    except ImportError as e:
                        raise RuntimeError(
                            "mlx-lm is not installed; use `uv sync --extra mlx`"
                        ) from e
                    try:
                        model, tokenizer = mlx_load(self._model_path)
                    except Exception as e:
                        raise RuntimeError(
                            f"could not load MLX model at {self._model_path}: {e}"
                        ) from e
                    # Gemma ends a turn with <turn|>; make sure decoding stops there.
                    try:
                        turn_id = tokenizer.convert_tokens_to_ids(STOP_TOKEN_TEXT)
                        if isinstance(turn_id, int) and turn_id >= 0:
                            tokenizer.eos_token_ids.add(turn_id)
                    except Exception:  # pragma: no cover - tokenizer quirks
                        pass
                    self._banned = [
                        tid
                        for tid in (tokenizer.convert_tokens_to_ids(t) for t in BANNED_TOKEN_TEXTS)
                        if isinstance(tid, int) and tid >= 0
                    ]
                    self._loaded = (model, tokenizer)
        return self._loaded

    def render(self, system: str, messages: list[Message]):
        """Token ids for the chat-templated prompt."""
        _, tokenizer = self.load()
        chat = [{"role": "system", "content": system}, *messages]
        return tokenizer.apply_chat_template(chat, add_generation_prompt=True, tokenize=True)

    def stream(self, system: str, messages: list[Message], max_tokens: int = 400) -> Iterator[str]:
        import mlx.core as mx
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_logits_processors, make_sampler

        model, tokenizer = self.load()
        prompt = self.render(system, messages)
        banned = self._banned

        def ban(_tokens, logits):
            if banned:
                logits[:, banned] = -mx.inf
            return logits

        with self._lock:
            produced = 0
            last = None
            try:
                for r in stream_generate(
                    model,
                    tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    sampler=make_sampler(self._temperature, self._top_p, top_k=self._top_k),
                    logits_processors=[
                        ban,
                        *make_logits_processors(
                            repetition_penalty=self._repetition_penalty,
                            repetition_context_size=64,
                        ),
                    ],
                ):
                    last = r
                    piece = r.text
                    if not piece:
                        continue
                    if STOP_TOKEN_TEXT in piece or "<|" in piece or "<eos>" in piece:
                        piece = strip_control(piece)
                        if piece:
                            yield piece
                        break
                    produced += 1
                    yield piece
            finally:
                if last is not None:
                    self.last_stats = {
                        "prompt_tokens": getattr(last, "prompt_tokens", None),
                        "prompt_tps": round(getattr(last, "prompt_tps", 0.0), 1),
                        "generation_tokens": getattr(last, "generation_tokens", None),
                        "generation_tps": round(getattr(last, "generation_tps", 0.0), 1),
                        "peak_memory_gb": round(getattr(last, "peak_memory", 0.0), 2),
                        "finish_reason": getattr(last, "finish_reason", None),
                    }
                    log.info("mlx.generated %s", self.last_stats)
                mx.clear_cache()
        if produced == 0:
            raise RuntimeError("mlx model returned an empty response")

    def generate(self, system: str, messages: list[Message], max_tokens: int = 400) -> str:
        text = strip_control("".join(self.stream(system, messages, max_tokens)))
        if not text:
            raise RuntimeError("mlx model returned an empty response")
        return text
