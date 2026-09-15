import os

import pytest
from fastapi.testclient import TestClient

import apps.api.main as api
from apps.api.main import app
from igihe_assistant.config import Settings
from igihe_assistant.generation.mlx_gen import MlxGenerator, strip_control

LIVE = os.environ.get("IGIHE_LIVE_MLX") == "1"
MODEL = os.environ.get("MLX_MODEL_PATH", "models/gemma-4-e2b-it-mlx")

client = TestClient(app)


def test_strip_control_removes_gemma_markers():
    assert strip_control("Yego [1].<turn|>\n<|turn>user\nx") == "Yego [1]."
    assert strip_control("<|channel>thought\nhmm<channel|>Yego [1].") == "Yego [1]."
    assert strip_control("Yego [1].") == "Yego [1]."


def test_settings_reads_mlx_model_path(monkeypatch):
    monkeypatch.setenv("MLX_MODEL_PATH", "models/some-mlx")
    monkeypatch.setenv("GENERATOR", "mlx")
    s = Settings()
    assert s.mlx_model_path == "models/some-mlx" and s.generator == "mlx"


def test_missing_model_dir_fails_fast_at_construction():
    with pytest.raises(FileNotFoundError):
        MlxGenerator("models/does-not-exist")


def test_unloadable_model_raises_at_generate_not_import(tmp_path):
    # Construction only checks the directory; load errors surface from
    # generate() so the API can fall back to the fake generator per request.
    gen = MlxGenerator(str(tmp_path))
    with pytest.raises(RuntimeError):
        gen.generate("SYS", [{"role": "user", "content": "amazi?"}], 10)


def test_ready_reports_mlx_model_id(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "generator", MlxGenerator(str(tmp_path)))
    ready = client.get("/health/ready").json()
    assert ready["model"] == f"mlx:{tmp_path.name}"


@pytest.mark.skipif(not os.path.isdir(MODEL), reason="needs the Gemma checkpoint on disk")
def test_chat_template_renders_system_and_alternating_turns():
    from transformers import AutoTokenizer

    from igihe_assistant.prompting.builder import build_messages

    tok = AutoTokenizer.from_pretrained(MODEL)
    system, messages = build_messages(
        "Amazi?", [{"title": "T", "published_at": "2024-01-01", "url": "u", "content": "C"}]
    )
    text = tok.apply_chat_template(
        [{"role": "system", "content": system}, *messages],
        add_generation_prompt=True, tokenize=False,
    )
    assert text.count("<|turn>system") == 1
    assert text.rstrip().endswith("<|turn>model")
    assert text.count("<|turn>user") == text.count("<|turn>model")


@pytest.mark.skipif(not LIVE, reason="needs local MLX weights at MLX_MODEL_PATH")
def test_mlx_generates_short_cited_kinyarwanda():
    from igihe_assistant.prompting.builder import build_messages

    gen = MlxGenerator(MODEL)
    system, messages = build_messages(
        "Umushinga w'amazi uzatwara angahe?",
        [{"title": "Amazi", "published_at": "2024-03-02", "url": "u",
          "content": "Umushinga w'amazi uzatwara miliyari 12 z'amafaranga y'u Rwanda."}],
    )
    text = gen.generate(system, messages, 60)
    assert text.strip() and "<|" not in text and "[1]" in text
