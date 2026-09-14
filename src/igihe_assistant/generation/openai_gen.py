"""OpenAI-backed generator: Chat Completions API, fake-compatible contract."""

from __future__ import annotations

import httpx


class OpenAIGenerator:
    """Calls OpenAI Chat Completions; raises on transport/model errors so the
    caller can fall back to the fake generator. The API key is kept in memory
    only and never logged."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: int = 120,
    ):
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required")
        if not model:
            raise ValueError("OPENAI_MODEL is required")
        self._model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    @property
    def model_id(self) -> str:
        return f"openai:{self._model}"

    def generate(self, prompt: str, sources: list[dict], max_tokens: int = 400) -> str:
        # Split the flat prompt back into system/user turns so the API can
        # apply the model's chat template; without it, small instruction
        # models echo the prompt instead of answering.
        from ..prompting.builder import build_messages

        head, _, tail = prompt.rpartition("Igisubizo:")
        question = head.rsplit("Ikibazo:", 1)[-1].strip()
        system, user = build_messages(question, sources)
        if tail.strip():
            user += "\n" + tail.strip()
        resp = httpx.post(
            self._base_url + "/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            },
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
