"""Конфигурация приложения.

Читается из окружения и `.env` (см. `.env.example`). Инфраструктурный слой —
здесь допустимы внешние зависимости (pydantic-settings), в отличие от домена.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    security_lab_path: Path = Field(
        default=Path.home() / "Desktop" / "security-lab",
        description="Корень репозитория security-lab (содержит toolkit/recon.py).",
    )

    # --- LLM ---
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-4-8"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    embed_model: str = "nomic-embed-text"
    llm_budget_usd: float | None = None
    # Дефолтный провайдер; фабрика откатится на ollama, если ключа anthropic нет.
    default_llm_provider: str = "anthropic"

    # --- RAG ---
    database_url: str = "postgresql://audit:audit@localhost:5432/audit"
    embed_dimension: int = 768  # размерность nomic-embed-text
    vector_store: str = "pgvector"  # какой бэкенд использовать: pgvector | qdrant
    qdrant_url: str = "http://localhost:6333"

    @property
    def recon_toolkit_path(self) -> Path:
        """Каталог `toolkit/`, откуда импортируется модуль `recon`."""
        return self.security_lab_path / "toolkit"


@lru_cache
def get_settings() -> Settings:
    return Settings()
