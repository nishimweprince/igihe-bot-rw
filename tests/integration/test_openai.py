import os

import pytest

import apps.api.main as api
from igihe_assistant.config import Settings
from igihe_assistant.generation.factory import build_generator
from igihe_assistant.generation.openai_gen import OpenAIGenerator

LIVE = os.environ.get("IGIHE_LIVE_OPENAI") == "1"
MSGS = [{"role": "user", "content": "Ikibazo: Amazi?"}]


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
    seen = _stub_post(monkeypatch, {"choices": [{"message": {"content": "Amazi meza [1]."}}]})
    gen = OpenAIGenerator("gpt-4o-mini", "sk-test")
    assert gen.model_id == "openai:gpt-4o-mini"
    text = gen.generate("SYS", MSGS, 60)
    assert text == "Amazi meza [1]."
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"] == {"Authorization": "Bearer sk-test"}
    assert seen["json"]["model"] == "gpt-4o-mini"
    assert seen["json"]["max_tokens"] == 60
    assert seen["json"]["stream"] is False
    assert [m["role"] for m in seen["json"]["messages"]] == ["system", "user"]
    assert seen["json"]["messages"][0]["content"] == "SYS"


def test_empty_response_raises(monkeypatch):
    _stub_post(monkeypatch, {"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(RuntimeError, match="empty response"):
        OpenAIGenerator("gpt-4o-mini", "sk-test").generate("SYS", MSGS, 10)


def test_unexpected_payload_raises(monkeypatch):
    _stub_post(monkeypatch, {"error": "boom"})
    with pytest.raises(RuntimeError, match="unexpected payload"):
        OpenAIGenerator("gpt-4o-mini", "sk-test").generate("SYS", MSGS, 10)


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


def test_openai_only_when_explicitly_selected(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("GENERATOR", "fake")
    assert build_generator(Settings()).model_id == "fake-gen-v1"
    monkeypatch.setenv("GENERATOR", "openai")
    gen = build_generator(Settings())
    assert gen.model_id == "openai:gpt-4o-mini"
    monkeypatch.setattr(api, "generator", gen)
    assert api.generator.model_id == "openai:gpt-4o-mini"


def test_unknown_generator_is_a_config_error(monkeypatch):
    monkeypatch.setenv("GENERATOR", "gpt5")
    with pytest.raises(ValueError, match="unknown GENERATOR"):
        build_generator(Settings())


@pytest.mark.skipif(not LIVE, reason="needs OPENAI_API_KEY and bills per request")
def test_openai_live_short_kinyarwanda():
    key = os.environ.get("OPENAI_API_KEY", "")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    gen = OpenAIGenerator(model, key)
    text = gen.generate(
        "Subiza mu Kinyarwanda gikeya cyane.", [{"role": "user", "content": "Uravuga iki?"}], 60
    )
    assert text.strip()
