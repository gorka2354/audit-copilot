"""Юнит-тест factory vectorstore: неизвестный бэкенд → ValueError (без инфры)."""

from __future__ import annotations

import pytest

from app.adapters.vectorstore.factory import build_store
from app.config import Settings


def test_build_store_rejects_unknown_backend() -> None:
    settings = Settings(vector_store="mongodb", _env_file=None)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="неизвестный vector_store"):
        build_store(settings)
