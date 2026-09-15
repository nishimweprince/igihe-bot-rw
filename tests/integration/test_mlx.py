import os

import pytest
from fastapi.testclient import TestClient

import apps.api.main as api
from apps.api.main import app
from igihe_assistant.config import Settings
from igihe_assistant.generation.mlx_gen import (
    MlxGenerator,
    render_alta_chatml,
    strip_alta_stop,
)

LIVE = os.environ.get("IGIHE_LIVE_MLX") == "1"
MODEL = os.environ.get("MLX_MODEL_PATH", "models/alta-sft-v1.0-mlx")

client = TestClient(app)


def test_chatml_render_matches_alta_reference():
    prompt = render_alta_chatml("SYS", "USER")
    assert prompt == (
        "<|im_start|>system\nSYS<|im_end|>\n"
        "<|im_start|>user\nUSER<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def test_strip_alta_stop_truncates_at_im_end():
    assert strip_alta_stop("Yego [1].<|im_end|>\n<|im_start|>user\nx") == "Yego [1]."
    assert strip_alta_stop("Yego [1].") == "Yego [1]."
    assert strip_alta_stop("Yego [1].Igisubizo:") == "Yego [1]."


def test_settings_reads_mlx_model_path(monkeypatch):
    monkeypatch.setenv("MLX_MODEL_PATH", "models/some-mlx")
    assert Settings().mlx_model_path == "models/some-mlx"


def test_missing_model_dir_fails_fast_at_construction():
    with pytest.raises(FileNotFoundError):
        MlxGenerator("models/does-not-exist")


def test_unloadable_model_raises_at_generate_not_import(tmp_path):
    # Construction only checks the directory; load errors surface from
    # generate() so the API can fall back to the fake generator per request.
    gen = MlxGenerator(str(tmp_path))
    with pytest.raises(RuntimeError):
        gen.generate("Ikibazo: amazi?\nIgisubizo:", [], 10)


def test_ready_reports_mlx_model_id(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "generator", MlxGenerator(str(tmp_path)))
    ready = client.get("/health/ready").json()
    assert ready["model"] == f"mlx:{tmp_path.name}"


@pytest.mark.skipif(not LIVE, reason="needs local MLX weights at MLX_MODEL_PATH")
def test_mlx_generates_short_kinyarwanda():
    gen = MlxGenerator(MODEL)
    text = gen.generate("Subiza mu Kinyarwanda gikeya cyane: uravuga iki?", [], 60)
    assert text.strip()
