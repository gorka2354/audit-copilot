"""Интеграция: API на реальном стеке — lifespan поднимает пул и адаптеры.

Проверяет, что сборка приложения (create_app + lifespan + DI) реально работает
против живого Postgres и движка security-lab. /health не ходит в сеть к LLM,
поэтому тест дёшев, но полноценно упражняет старт стека. Skip, если инфры нет.
"""

from __future__ import annotations

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import get_settings


@pytest.mark.integration
def test_health_on_real_stack() -> None:
    settings = get_settings()
    if not settings.recon_toolkit_path.exists():
        pytest.skip("security-lab недоступен — задай SECURITY_LAB_PATH")
    try:
        psycopg.connect(settings.database_url, connect_timeout=3).close()
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    # `with` запускает lifespan: from_dsn_pool к Postgres, анализатор, эмбеддер, роутер
    with TestClient(create_app()) as client:
        resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["providers"]  # роутер собрал хотя бы одного провайдера
