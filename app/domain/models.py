"""Доменные модели.

Чистый слой: только стандартная библиотека, никаких зависимостей от фреймворков,
БД или конкретных движков анализа. Всё, что приходит из инфраструктуры (recon,
LLM, векторное хранилище), нормализуется в эти типы на границе адаптеров.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Серьёзность находки.

    На этапе статического анализа выводится из приоритета детектора; позже
    AI-слой (L4) может пересмотреть её с опорой на контекст и базу знаний.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class SoliditySource:
    """Единица кода на вход анализатору.

    `path` — относительный путь. Он не только якорь для строк в отчёте: часть
    детекторов security-lab понижает приоритет для путей вида `test/`, `mock/`,
    `script/`, поэтому путь влияет и на severity. `code` — исходный текст контракта.
    """

    path: str
    code: str


@dataclass(frozen=True, slots=True)
class CodeLocation:
    """Место в коде, к которому привязана находка.

    `line` обычно 1-based; отдельные детекторы могут вернуть 0, когда точную
    строку установить не удалось.
    """

    file: str
    line: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass(frozen=True, slots=True)
class Finding:
    """Нормализованная находка статического анализа — «сырой» сигнал до триажа.

    Здесь ещё нет ни SWC/CWE, ни цитат, ни итогового вердикта: их добавляет
    AI-слой на следующих инкрементах. Поле остаётся неизменяемым (frozen),
    чтобы находки можно было безопасно дедуплицировать и хранить.
    """

    detector: str
    """Стабильный ключ детектора (например `access`, `spotoracle`)."""

    title: str
    """Человекочитаемый класс уязвимости — заголовок детектора."""

    location: CodeLocation
    snippet: str
    note: str
    severity: Severity
    source: str = "security-lab"
    """Какой анализатор породил находку — для мультидвижковой атрибуции."""
