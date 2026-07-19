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
from app.domain.rag import Chunk, RetrievedChunk


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


@runtime_checkable
class Embedder(Protocol):
    """Модель эмбеддингов: текст → вектор фиксированной размерности."""

    name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Векторизовать батч текстов (порядок сохраняется)."""
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Хранилище векторов с семантическим поиском."""

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """Идемпотентно сохранить фрагменты с их эмбеддингами (upsert по `Chunk.id`)."""
        ...

    def replace_source(
        self, source: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        """Атомарно заменить ВСЕ фрагменты документа `source` новыми.

        Удаляет прежние чанки источника и вставляет актуальные в одной транзакции —
        это защищает от orphan-чанков при переиндексации сжавшегося документа.
        """
        ...

    def search(
        self, query_embedding: list[float], *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        """top-k ближайших фрагментов (dense/cosine). `vuln_class` сужает до класса + general."""
        ...

    def search_text(
        self, query: str, *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        """Полнотекстовый (BM25) поиск. `vuln_class` сужает до класса + general."""
        ...
