"""Адаптер Anthropic (Claude) за портом `LLMProvider` — через официальный SDK.

Для Python официальный `anthropic` SDK — канон (ретраи, типизированный usage,
prompt-caching), поэтому здесь не используем httpx напрямую. Стоимость считаем
из `usage` по прайсингу модели.
"""

from __future__ import annotations

import time
from typing import Any

import anthropic
from anthropic.types import MessageParam, TextBlock

from app.domain.llm import LLMResponse, Message, Role, TokenUsage

# USD за 1M токенов: (input, output). Источник — Anthropic pricing.
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}
_DEFAULT_MAX_TOKENS = 4096


class AnthropicProvider:
    """`LLMProvider` поверх Anthropic Messages API."""

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-opus-4-8",
        client: anthropic.Anthropic | None = None,
    ):
        self.model = model
        self._client = client or anthropic.Anthropic(api_key=api_key)

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # temperature намеренно не прокидываем: Opus 4.8/4.7 и Sonnet 5 его отвергают (400).
        system, conversation = self._split_system(messages)

        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
            "messages": conversation,
        }
        if system:  # Anthropic system — отдельное поле; опускаем, если пусто
            request["system"] = system

        started = time.perf_counter()
        response = self._client.messages.create(**request)
        latency_ms = (time.perf_counter() - started) * 1000.0

        text = "".join(block.text for block in response.content if isinstance(block, TextBlock))
        usage = TokenUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            usage=usage,
            cost_usd=self._cost(usage),
            latency_ms=latency_ms,
        )

    def _cost(self, usage: TokenUsage) -> float:
        price_in, price_out = _PRICING.get(self.model, (0.0, 0.0))
        return usage.prompt_tokens / 1e6 * price_in + usage.completion_tokens / 1e6 * price_out

    @staticmethod
    def _split_system(messages: list[Message]) -> tuple[str, list[MessageParam]]:
        """Anthropic принимает system-промпт отдельным полем, а не в messages."""
        system = "\n\n".join(m.content for m in messages if m.role is Role.SYSTEM)
        conversation: list[MessageParam] = [
            {"role": m.role.value, "content": m.content}  # type: ignore[typeddict-item]
            for m in messages
            if m.role is not Role.SYSTEM
        ]
        return system, conversation
