"""Доменные модели аудиторского отчёта — обогащённые находки с провенансом.

Провенанс железный: `AuditFinding.detector` приходит из recon (находка не рождается
без детектора), а `citations` — только проверенные фрагменты переданного RAG-контекста.
LLM обогащает (severity/rationale/fix/цитаты), но не создаёт находки из воздуха.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.models import CodeLocation, Severity


@dataclass(frozen=True, slots=True)
class Citation:
    """Ссылка на источник из базы знаний, подкрепляющая находку."""

    source: str
    snippet: str


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """Находка аудита: детерминированный сигнал детектора + LLM-обогащение."""

    detector: str
    """Стабильный ключ детектора recon — провенанс находки."""

    title: str
    location: CodeLocation
    snippet: str
    severity: Severity
    rationale: str
    fix: str
    citations: list[Citation] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Отчёт по одному контракту."""

    contract: str
    findings: list[AuditFinding]

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity is Severity.HIGH)
