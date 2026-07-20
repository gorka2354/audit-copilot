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

from app.domain.llm import LLMError, LLMResponse, Message, Role, TokenUsage

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
        timeout: float = 120.0,
        client: anthropic.Anthropic | None = None,
    ):
        if model not in _PRICING:
            raise ValueError(
                f"нет прайсинга для модели '{model}': стоимость посчиталась бы как 0 "
                f"и бюджет-гард ослеп бы. Добавь её в _PRICING. Известные: {sorted(_PRICING)}"
            )
        self.model = model
        # Явный таймаут: SDK по умолчанию ~600с, что под sync-в-threadpool держит поток и
        # слот пула минутами. Инъектированный client (тесты) уважаем как есть.
        self._client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout)

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        # temperature не прокидываем: дефолтные Opus 4.8/4.7 и Sonnet 5 его отвергают (400),
        # а для аудита детерминизм (t=0) предпочтителен. Модели, которые temperature
        # ПРИНИМАЮТ (Haiku 4.5, Sonnet 4.6), тоже получают детерминированный вывод — это
        # осознанная асимметрия с Ollama-адаптером (тот temperature прокидывает).
        system, conversation = self._split_system(messages)
        if not conversation:
            raise LLMError(
                "пустой диалог: Anthropic отвергает messages=[] — нужен user/assistant-месседж",
                retryable=False,
                provider=self.name,
            )

        request: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens if max_tokens is not None else _DEFAULT_MAX_TOKENS,
            "messages": conversation,
        }
        if system:  # Anthropic system — отдельное поле; опускаем, если пусто
            request["system"] = system

        started = time.perf_counter()
        try:
            response = self._client.messages.create(**request)
        except anthropic.APIStatusError as exc:
            # 429 и 5xx транзиентны (fallback уместен); 4xx (401/400/…) — терминальны.
            retryable = exc.status_code == 429 or exc.status_code >= 500
            raise LLMError(
                f"Anthropic HTTP {exc.status_code}: {exc}",
                retryable=retryable,
                provider=self.name,
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(
                f"Anthropic connection error: {exc}", retryable=True, provider=self.name
            ) from exc
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
        price_in, price_out = _PRICING[self.model]  # model валидирован в __init__
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
