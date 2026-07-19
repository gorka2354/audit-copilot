"""Порты домена — интерфейсы, через которые домен общается с инфраструктурой.

Используем `typing.Protocol` (структурная типизация): адаптерам не нужно
наследоваться от базового класса — достаточно совпасть по форме. Это держит
конкретные движки (security-lab, Slither, LLM-провайдеры, векторные БД) полностью
за границей и делает их взаимозаменяемыми.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.llm import LLMResponse, Message
from app.domain.models import Finding, SoliditySource


@runtime_checkable
class StaticAnalyzer(Protocol):
    """Статический анализатор Solidity-кода.

    Реализации оборачивают конкретный движок (например `recon.py` из
    security-lab) и возвращают уже нормализованные находки домена.
    """

    name: str
    """Идентификатор движка — попадает в `Finding.source`."""

    def analyze(self, source: SoliditySource) -> list[Finding]:
        """Проанализировать один контракт и вернуть список находок."""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    """Провайдер генерации текста (Ollama, Anthropic, OpenAI, …).

    Реализация переводит доменные `Message` в вызов конкретного API и
    возвращает единый `LLMResponse` с расходом токенов и стоимостью.
    """

    name: str
    """Идентификатор провайдера (`ollama`, `anthropic`, …)."""

    model: str
    """Идентификатор используемой модели."""

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Сгенерировать ответ на последовательность сообщений."""
        ...
