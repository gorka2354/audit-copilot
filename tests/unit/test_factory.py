"""Юнит-тесты фабрики роутера (композиционный корень LLM-слоя)."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr

from app.adapters.llm.factory import build_router
from app.config import Settings


def _settings(**overrides: Any) -> Settings:
    # _env_file=None изолирует тест от локального .env.
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_registers_anthropic_when_key_present() -> None:
    router = build_router(
        _settings(anthropic_api_key=SecretStr("sk-test"), default_llm_provider="anthropic")
    )
    assert "anthropic" in router.provider_names
    assert "ollama" in router.provider_names
    assert router.default == "anthropic"


def test_falls_back_to_ollama_without_key() -> None:
    router = build_router(_settings(anthropic_api_key=None, default_llm_provider="anthropic"))
    assert "anthropic" not in router.provider_names
    assert router.provider_names == ["ollama"]
    assert router.default == "ollama"  # выбранный дефолт недоступен → откат


def test_provider_keys_match_provider_names() -> None:
    # Ключ роутера обязан совпадать с provider.name (иначе рассинхрон из ревью Инкр1).
    router = build_router(_settings(anthropic_api_key=SecretStr("sk-test")))
    assert set(router.provider_names) == {"anthropic", "ollama"}
