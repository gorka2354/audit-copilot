"""Адаптер к движку security-lab: `toolkit/recon.py` (46 статических детекторов).

Мост тонкий и однонаправленный — импортирует `recon` из указанного каталога и
вызывает его публичные функции. Сам security-lab при этом **не модифицируется**:
мы только читаем. Наружу отдаём нормализованные доменные `Finding`.

`recon.detect_all(text, rel)` возвращает ``{title: [(rel, line, snippet, note, prio)]}``,
где `prio` 0/1/2 — приоритет (high/medium/low). Стабильный ключ детектора даёт
`recon.det_key(title)`. Модуль зависит только от stdlib и работает офлайн.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Protocol, cast

from app.domain.models import CodeLocation, Finding, Severity, SoliditySource

_PRIO_TO_SEVERITY: dict[int, Severity] = {
    0: Severity.HIGH,
    1: Severity.MEDIUM,
    2: Severity.LOW,
}

# Лиды одного детектора: (rel_path, line, snippet, note, prio).
Lead = tuple[str, int, str, str, int]


class ReconEngine(Protocol):
    """То, что нам нужно от модуля `recon` — явный контракт вместо `ModuleType`.

    Под него структурно подходят и реальный модуль, и тестовый дубль.
    """

    def detect_all(self, text: str, rel: str) -> dict[str, list[Lead]]:
        ...

    def det_key(self, title: str) -> str:
        ...


class SecurityLabAnalyzer:
    """Реализация порта `StaticAnalyzer` поверх `recon.py`."""

    name = "security-lab"

    def __init__(self, recon: ReconEngine):
        self._recon = recon

    @classmethod
    def from_path(cls, toolkit_path: Path) -> SecurityLabAnalyzer:
        """Собрать анализатор, импортировав `recon` из каталога `toolkit/`."""
        return cls(cls._load_recon(toolkit_path))

    @staticmethod
    def _load_recon(toolkit_path: Path) -> ReconEngine:
        recon_file = toolkit_path / "recon.py"
        if not recon_file.exists():
            raise FileNotFoundError(
                f"recon.py не найден в {toolkit_path}. Проверь SECURITY_LAB_PATH в .env."
            )
        path_str = str(toolkit_path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
        try:
            # recon импортируется динамически (внешний движок) — сужаем тип до ReconEngine.
            return cast(ReconEngine, importlib.import_module("recon"))
        except ImportError as exc:  # pragma: no cover - защитная ветка
            raise RuntimeError(f"Не удалось импортировать recon из {toolkit_path}: {exc}") from exc

    def analyze(self, source: SoliditySource) -> list[Finding]:
        raw = self._recon.detect_all(source.code, source.path)
        findings: list[Finding] = []
        for title, leads in raw.items():
            detector = self._recon.det_key(title)
            for rel, line, snippet, note, prio in leads:
                findings.append(
                    Finding(
                        detector=detector,
                        title=title,
                        location=CodeLocation(file=rel, line=int(line)),
                        snippet=snippet.strip(),
                        note=note.strip(),
                        severity=_PRIO_TO_SEVERITY.get(prio, Severity.LOW),
                        source=self.name,
                    )
                )
        return findings
