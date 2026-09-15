"""Runtime configuration from environment (no secrets committed)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    # -- generation --------------------------------------------------------
    #: Explicit choice: fake | mlx | openai | ollama (no implicit precedence).
    generator: str = field(default_factory=lambda: _env("GENERATOR", "fake"))
    mlx_model_path: str = field(default_factory=lambda: _env("MLX_MODEL_PATH"))
    mlx_temperature: float = field(default_factory=lambda: _float("MLX_TEMPERATURE", 0.4))
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL"))
    openai_base_url: str = field(
        default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    ollama_base_url: str = field(
        default_factory=lambda: _env("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL"))
    warmup: bool = field(default_factory=lambda: _bool("WARMUP", True))
    max_output_tokens: int = field(default_factory=lambda: _int("MAX_OUTPUT_TOKENS", 200))
    max_concurrent_generations: int = field(
        default_factory=lambda: _int("MAX_CONCURRENT_GENERATIONS", 1)
    )
    validation_retry: bool = field(default_factory=lambda: _bool("VALIDATION_RETRY", False))
    history_turns: int = field(default_factory=lambda: _int("HISTORY_TURNS", 6))

    # -- index / retrieval ---------------------------------------------------
    #: Persistent index file; empty = build in memory from SAMPLE_DIR/fixtures.
    index_path: str = field(default_factory=lambda: _env("INDEX_PATH"))
    sample_dir: str = field(default_factory=lambda: _env("SAMPLE_DIR"))
    sqlite_cache_mb: int = field(default_factory=lambda: _int("SQLITE_CACHE_MB", 128))
    candidates_n: int = field(default_factory=lambda: _int("CANDIDATES_N", 200))
    min_coverage: float = field(default_factory=lambda: _float("MIN_COVERAGE", 0.5))
    recency_weight: float = field(default_factory=lambda: _float("RECENCY_WEIGHT", 0.3))
    recency_half_life_days: float = field(
        default_factory=lambda: _float("RECENCY_HALF_LIFE_DAYS", 365.0)
    )
    recency_window_days: int = field(default_factory=lambda: _int("RECENCY_WINDOW_DAYS", 180))
    reranker_model: str = field(default_factory=lambda: _env("RERANKER_MODEL"))
    max_evidence_sources: int = field(default_factory=lambda: _int("MAX_EVIDENCE_SOURCES", 4))
    max_evidence_chars: int = field(default_factory=lambda: _int("MAX_EVIDENCE_CHARS", 1000))

    # -- API -----------------------------------------------------------------
    max_query_chars: int = field(default_factory=lambda: _int("MAX_QUERY_CHARS", 500))
    log_content: bool = field(default_factory=lambda: _bool("LOG_CONTENT", False))

    # -- ingestion -------------------------------------------------------------
    raw_storage_root: str = field(default_factory=lambda: _env("RAW_STORAGE_ROOT", "data/raw"))
    wordpress_base_url: str = field(
        default_factory=lambda: _env("WORDPRESS_BASE_URL", "https://old.igihe.com")
    )
    ingest_concurrency: int = field(default_factory=lambda: _int("INGEST_CONCURRENCY", 2))
