"""Explicit generator selection: GENERATOR=mlx|openai|ollama|fake."""

from __future__ import annotations

from ..config import Settings
from .generator import FakeGenerator
from .mlx_gen import MlxGenerator
from .ollama_gen import OllamaGenerator
from .openai_gen import OpenAIGenerator

CHOICES = ("fake", "mlx", "openai", "ollama")


def build_generator(settings: Settings):
    kind = (settings.generator or "fake").lower()
    if kind == "fake":
        return FakeGenerator()
    if kind == "mlx":
        if not settings.mlx_model_path:
            raise ValueError("GENERATOR=mlx requires MLX_MODEL_PATH")
        return MlxGenerator(settings.mlx_model_path, temperature=settings.mlx_temperature)
    if kind == "openai":
        return OpenAIGenerator(
            settings.openai_model, settings.openai_api_key, settings.openai_base_url
        )
    if kind == "ollama":
        if not settings.ollama_model:
            raise ValueError("GENERATOR=ollama requires OLLAMA_MODEL")
        return OllamaGenerator(settings.ollama_model, settings.ollama_base_url)
    raise ValueError(f"unknown GENERATOR={settings.generator!r}; expected one of {CHOICES}")
