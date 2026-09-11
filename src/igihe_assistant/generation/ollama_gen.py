"""Ollama-backed generator: pinned local Llama, fake-compatible contract."""

from __future__ import annotations

import json
import urllib.request


class OllamaGenerator:
    """Calls a local Ollama model; raises on transport/model errors so the
    caller can fall back to the fake generator."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 timeout_s: int = 120):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    @property
    def model_id(self) -> str:
        return f"ollama:{self._model}"

    def generate(self, prompt: str, sources: list[dict], max_tokens: int = 400) -> str:
        # Split the flat prompt back into system/user turns so Ollama can
        # apply the model's chat template; without it, small instruction
        # models echo the prompt instead of answering.
        from ..prompting.builder import build_messages

        head, _, tail = prompt.rpartition("Igisubizo:")
        question = head.rsplit("Ikibazo:", 1)[-1].strip()
        system, user = build_messages(question, sources)
        if tail.strip():
            user += "\n" + tail.strip()
        body = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.2},
        }).encode("utf-8")
        req = urllib.request.Request(
            self._base_url + "/api/chat", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = ((payload.get("message") or {}).get("content") or "").strip()
        if not text:
            raise RuntimeError("ollama returned an empty response")
        return text
