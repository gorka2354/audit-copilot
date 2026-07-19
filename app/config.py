"""Конфигурация приложения.

Читается из окружения и `.env` (см. `.env.example`). Инфраструктурный слой —
здесь допустимы внешние зависимости (pydantic-settings), в отличие от домена.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    security_lab_path: Path = Field(
        default=Path.home() / "Desktop" / "security-lab",
        description="Корень репозитория security-lab (содержит toolkit/recon.py).",
    )

    @property
    def recon_toolkit_path(self) -> Path:
        """Каталог `toolkit/`, откуда импортируется модуль `recon`."""
        return self.security_lab_path / "toolkit"


@lru_cache
def get_settings() -> Settings:
    return Settings()
