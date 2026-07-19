"""Доменные типы RAG-слоя.

Чистый Python: фрагмент корпуса знаний и результат поиска. Ни эмбеддеры,
ни векторное хранилище тут не фигурируют — только данные, которыми они обмениваются.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Chunk:
    """Фрагмент документа из корпуса знаний по безопасности."""

    id: str
    """Стабильный ключ — источник + порядковый номер (для идемпотентного upsert)."""

    source: str
    """Откуда фрагмент (путь/имя документа) — попадёт в цитату."""

    content: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    """Фрагмент, найденный по запросу, с оценкой релевантности."""

    chunk: Chunk
    score: float
