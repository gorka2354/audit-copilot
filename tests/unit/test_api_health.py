"""Юнит: /health через TestClient с подменённой зависимостью (без lifespan/инфры)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_router


class _FakeRouter:
    name = "router"
    model = "fake-model"
    default = "anthropic"
    provider_names = ["anthropic", "ollama"]


def _client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_router] = _FakeRouter
    # TestClient без `with` не запускает lifespan → реальные адаптеры не поднимаются
    return TestClient(app)


def test_health_ok() -> None:
    resp = _client().get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "anthropic"
    assert body["model"] == "fake-model"
    assert body["providers"] == ["anthropic", "ollama"]
