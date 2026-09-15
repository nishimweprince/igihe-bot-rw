"""Ollama-backed generator (local models), NDJSON streaming."""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Iterator

from ..prompting.builder import Message


class OllamaGenerator:
    """Raises on transport/model errors so the caller can fall back."""

    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 timeout_s: int = 120):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    @property
    def model_id(self) -> str:
        return f"ollama:{self._model}"

    def _request(self, system: str, messages: list[Message], max_tokens: int, stream: bool):
        body = json.dumps({
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": stream,
            "options": {"num_predict": max_tokens, "temperature": 0.2},
        }).encode("utf-8")
        req = urllib.request.Request(
            self._base_url + "/api/chat", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        return urllib.request.urlopen(req, timeout=self._timeout_s)

    def stream(self, system: str, messages: list[Message], max_tokens: int = 400) -> Iterator[str]:
        produced = 0
        with self._request(system, messages, max_tokens, True) as resp:
            for raw in resp:
                line = raw.decode("utf-8").strip()
                if not line:
                    continue
                payload = json.loads(line)
                piece = (payload.get("message") or {}).get("content") or ""
                if piece:
                    produced += 1
                    yield piece
                if payload.get("done"):
                    break
        if produced == 0:
            raise RuntimeError("ollama returned an empty response")

    def generate(self, system: str, messages: list[Message], max_tokens: int = 400) -> str:
        with self._request(system, messages, max_tokens, False) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = ((payload.get("message") or {}).get("content") or "").strip()
        if not text:
            raise RuntimeError("ollama returned an empty response")
        return text
