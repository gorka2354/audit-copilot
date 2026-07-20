"""Доменные типы для работы с LLM.

Чистый слой: описывает разговор и результат генерации в терминах, не зависящих
от конкретного провайдера. Адаптеры (Ollama, Anthropic, OpenAI) переводят свои
ответы в эти типы, поэтому остальной код одинаково работает с любым из них.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Расход токенов за один вызов."""

    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
        )


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Результат генерации, единый для всех провайдеров."""

    text: str
    model: str
    provider: str
    usage: TokenUsage
    cost_usd: float
    latency_ms: float
    degraded: bool = False
    """Ответ не от основного провайдера (fallback) — качество суждения могло упасть."""


class LLMError(RuntimeError):
    """Ошибка вызова LLM за портом.

    `retryable=True` — сбой транзиентный (сеть, 429, 5xx): роутеру уместно
    попробовать следующего провайдера. `retryable=False` — терминальная ошибка
    (неверный ключ, битый запрос): маскировать её тихим fallback нельзя.
    """

    def __init__(self, message: str, *, retryable: bool, provider: str | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.provider = provider
