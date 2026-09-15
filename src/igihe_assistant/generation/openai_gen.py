"""OpenAI-backed generator: Chat Completions with SSE streaming."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from ..prompting.builder import Message


class OpenAIGenerator:
    """Explicit opt-in (`GENERATOR=openai`). Raises on transport/model errors
    so the caller can fall back to the fake generator. The API key is kept in
    memory only and never logged."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: int = 120,
        temperature: float = 0.2,
    ):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")
        if not model:
            raise ValueError("OPENAI_MODEL is required")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._temperature = temperature

    @property
    def model_id(self) -> str:
        return f"openai:{self._model}"

    def _payload(self, system: str, messages: list[Message], max_tokens: int, stream: bool) -> dict:
        return {
            "model": self._model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": self._temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._api_key}"}

    def stream(self, system: str, messages: list[Message], max_tokens: int = 400) -> Iterator[str]:
        produced = 0
        with httpx.stream(
            "POST",
            self._base_url + "/chat/completions",
            headers=self._headers(),
            json=self._payload(system, messages, max_tokens, True),
            timeout=self._timeout_s,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
                    raise RuntimeError(f"openai returned an unexpected payload: {e}") from e
                if delta:
                    produced += 1
                    yield delta
        if produced == 0:
            raise RuntimeError("openai returned an empty response")

    def generate(self, system: str, messages: list[Message], max_tokens: int = 400) -> str:
        resp = httpx.post(
            self._base_url + "/chat/completions",
            headers=self._headers(),
            json=self._payload(system, messages, max_tokens, False),
            timeout=self._timeout_s,
        )
        resp.raise_for_status()
        try:
            text = resp.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"openai returned an unexpected payload: {e}") from e
        text = text.strip()
        if not text:
            raise RuntimeError("openai returned an empty response")
        return text
