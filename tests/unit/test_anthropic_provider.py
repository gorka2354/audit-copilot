"""Юнит-тесты Anthropic-провайдера — с фейковым SDK-клиентом (без сети)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anthropic
import pytest
from anthropic.types import TextBlock

from app.adapters.llm.anthropic import AnthropicProvider
from app.domain.llm import LLMError, Message, Role


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[TextBlock(type="text", text="Reentrancy is dangerous.", citations=None)],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
        )


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def _provider() -> tuple[AnthropicProvider, _FakeClient]:
    fake = _FakeClient()
    provider = AnthropicProvider(
        api_key="test", model="claude-opus-4-8", client=cast(anthropic.Anthropic, fake)
    )
    return provider, fake


def test_maps_usage_and_computes_cost() -> None:
    provider, _ = _provider()
    resp = provider.generate([Message(Role.USER, "чем опасна reentrancy?")], max_tokens=128)

    assert resp.provider == "anthropic"
    assert resp.model == "claude-opus-4-8"
    assert resp.text == "Reentrancy is dangerous."
    assert resp.usage.prompt_tokens == 1000
    assert resp.usage.completion_tokens == 500
    # 1000/1e6*$5 + 500/1e6*$25 = 0.005 + 0.0125
    assert abs(resp.cost_usd - 0.0175) < 1e-9


def test_extracts_system_prompt_and_omits_temperature() -> None:
    provider, fake = _provider()
    provider.generate(
        [
            Message(Role.SYSTEM, "You are a Solidity auditor."),
            Message(Role.USER, "audit this"),
        ]
    )

    sent = fake.messages.calls[0]
    assert sent["system"] == "You are a Solidity auditor."
    assert sent["messages"] == [{"role": "user", "content": "audit this"}]
    assert "temperature" not in sent  # Opus 4.8 отвергает temperature — не прокидываем


def test_defaults_max_tokens_when_absent() -> None:
    provider, fake = _provider()
    provider.generate([Message(Role.USER, "hi")])
    assert fake.messages.calls[0]["max_tokens"] == 4096


def test_rejects_model_without_pricing() -> None:
    # Модель без прайсинга дала бы cost=0 и ослепила бюджет-гард — падаем на старте.
    with pytest.raises(ValueError, match="прайсинг"):
        AnthropicProvider(api_key="x", model="claude-unknown-9")


def test_empty_conversation_raises() -> None:
    provider, _ = _provider()
    with pytest.raises(LLMError):
        provider.generate([Message(Role.SYSTEM, "only system, no user")])


def test_max_tokens_zero_is_passed_verbatim() -> None:
    provider, fake = _provider()
    provider.generate([Message(Role.USER, "hi")], max_tokens=0)
    assert fake.messages.calls[0]["max_tokens"] == 0  # 0 не подменяется дефолтом
