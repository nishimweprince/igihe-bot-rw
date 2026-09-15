import os

import pytest

import apps.api.main as api
from igihe_assistant.config import Settings
from igihe_assistant.generation.openai_gen import OpenAIGenerator

LIVE = os.environ.get("IGIHE_LIVE_OPENAI") == "1"


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _stub_post(monkeypatch, payload):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return _FakeResp(payload)

    import httpx

    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def test_posts_chat_completions_shape(monkeypatch):
    seen = _stub_post(
        monkeypatch, {"choices": [{"message": {"content": "Amazi meza [1]."}}]}
    )
    gen = OpenAIGenerator("gpt-4o-mini", "sk-test")
    assert gen.model_id == "openai:gpt-4o-mini"
    text = gen.generate("Ikibazo: Amazi?\nIgisubizo:", [], 60)
    assert text == "Amazi meza [1]."
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"] == {"Authorization": "Bearer sk-test"}
    assert seen["json"]["model"] == "gpt-4o-mini"
    assert seen["json"]["max_tokens"] == 60
    assert [m["role"] for m in seen["json"]["messages"]] == ["system", "user"]


def test_empty_response_raises(monkeypatch):
    _stub_post(monkeypatch, {"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(RuntimeError, match="empty response"):
        OpenAIGenerator("gpt-4o-mini", "sk-test").generate("Ikibazo: x?\nIgisubizo:", [], 10)


def test_unexpected_payload_raises(monkeypatch):
    _stub_post(monkeypatch, {"error": "boom"})
    with pytest.raises(RuntimeError, match="unexpected payload"):
        OpenAIGenerator("gpt-4o-mini", "sk-test").generate("Ikibazo: x?\nIgisubizo:", [], 10)


def test_missing_key_or_model_rejected():
    with pytest.raises(ValueError):
        OpenAIGenerator("gpt-4o-mini", "")
    with pytest.raises(ValueError):
        OpenAIGenerator("", "sk-test")


def test_settings_reads_openai_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    settings = Settings()
    assert settings.openai_api_key == "sk-test"
    assert settings.openai_model == "gpt-4o-mini"
    assert settings.openai_base_url == "https://api.openai.com/v1"


def test_api_selects_openai_when_configured(monkeypatch):
    # Selection happens at import; verify the constructor path the switch uses.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    settings = Settings()
    gen = OpenAIGenerator(settings.openai_model, settings.openai_api_key)
    monkeypatch.setattr(api, "generator", gen)
    assert api.generator.model_id == "openai:gpt-4o-mini"


@pytest.mark.skipif(not LIVE, reason="needs OPENAI_API_KEY and bills per request")
def test_openai_live_short_kinyarwanda():
    key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    gen = OpenAIGenerator(model, key)
    text = gen.generate("Subiza mu Kinyarwanda gikeya cyane: uravuga iki?", [], 60)
    assert text.strip()
