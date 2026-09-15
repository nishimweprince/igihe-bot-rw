import os

import pytest

import apps.api.main as api
from igihe_assistant.generation.ollama_gen import OllamaGenerator

LIVE = os.environ.get("IGIHE_LIVE_OLLAMA") == "1"


@pytest.mark.skipif(not LIVE, reason="needs local Ollama with llama3.2:3b pulled")
def test_ollama_generates_short_kinyarwanda():
    gen = OllamaGenerator("llama3.2:3b")
    text = gen.generate("Subiza mu Kinyarwanda gikeya cyane: uravuga iki?", [], 60)
    assert text.strip()


def test_generator_failure_falls_back_to_fake(monkeypatch):
    class Boom:
        model_id = "boom"

        def generate(self, prompt, sources, max_tokens=400):
            raise RuntimeError("model down")

    monkeypatch.setattr(api, "generator", Boom())
    text, _, _ = api.answer_question("Amazi meza i Kigali?", {})
    assert "[1]" in text or "nta bimenyetso" in text.lower()
