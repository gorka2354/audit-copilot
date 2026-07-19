"""Юнит: валидация конфигурации PgVectorStore (без сети — проверка до подключения)."""

from __future__ import annotations

import pytest

from app.adapters.vectorstore.pgvector_store import PgVectorStore


def test_requires_a_source() -> None:
    with pytest.raises(ValueError, match="ровно один источник"):
        PgVectorStore()


def test_rejects_multiple_sources() -> None:
    # dsn + pool одновременно — конфликт ловится до попытки соединения
    with pytest.raises(ValueError, match="ровно один источник"):
        PgVectorStore("postgresql://x", pool=object())  # type: ignore[arg-type]
