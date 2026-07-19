"""Pydantic-DTO HTTP-слоя.

Граница между доменом и HTTP: домен — frozen dataclass'ы без зависимостей, эти
DTO — их сериализуемое представление. Конвертация домен→DTO живёт здесь
(`from_domain`), домен про pydantic и HTTP не знает.
"""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Живость процесса и конфигурация LLM (без сетевых проверок)."""

    status: str
    llm_provider: str
    model: str
    providers: list[str]
