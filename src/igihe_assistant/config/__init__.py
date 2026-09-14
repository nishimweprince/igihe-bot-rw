"""Runtime configuration from environment (no secrets committed)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    database_url: str = field(
        default_factory=lambda: os.environ.get("DATABASE_URL", "sqlite:///data/assistant.db")
    )
    raw_storage_root: str = field(
        default_factory=lambda: os.environ.get("RAW_STORAGE_ROOT", "data/raw")
    )
    wordpress_base_url: str = field(
        default_factory=lambda: os.environ.get("WORDPRESS_BASE_URL", "https://old.igihe.com")
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", ""))
    mlx_model_path: str = field(
        default_factory=lambda: os.environ.get("MLX_MODEL_PATH", "")
    )
    openai_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY", "")
    )
    openai_model: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL", ""))
    openai_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        )
    )
    embedding_model: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "fake-hash-v1")
    )
    embedding_model_revision: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_MODEL_REVISION", "v1")
    )
    reranker_model: str = field(default_factory=lambda: os.environ.get("RERANKER_MODEL", ""))
    backend: str = field(default_factory=lambda: os.environ.get("BACKEND", "fixture"))
    retrieval_candidates: str = field(
        default_factory=lambda: os.environ.get("RETRIEVAL_CANDIDATES", "hybrid")
    )
    max_query_chars: int = field(default_factory=lambda: _int("MAX_QUERY_CHARS", 500))
    max_context_tokens: int = field(default_factory=lambda: _int("MAX_CONTEXT_TOKENS", 3000))
    max_output_tokens: int = field(default_factory=lambda: _int("MAX_OUTPUT_TOKENS", 400))
    max_evidence_sources: int = field(default_factory=lambda: _int("MAX_EVIDENCE_SOURCES", 6))
    max_evidence_chars: int = field(
        default_factory=lambda: _int("MAX_EVIDENCE_CHARS", 2000)
    )
    max_concurrent_generations: int = field(
        default_factory=lambda: _int("MAX_CONCURRENT_GENERATIONS", 4)
    )
    ingest_concurrency: int = field(default_factory=lambda: _int("INGEST_CONCURRENCY", 2))
    log_content: bool = field(
        default_factory=lambda: os.environ.get("LOG_CONTENT", "false").lower() == "true"
    )
