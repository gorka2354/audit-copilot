"""Адаптер `StaticAnalyzer`, воспроизводящий записанный вывод реального движка.

Record/replay: реальный security-lab прогоняется один раз
(`scripts/record_findings.py`), его нормализованные `Finding` сериализуются в
`assets/eval/replay/*.json` и коммитятся. `ReplayAnalyzer` читает их — так eval и
demo дают РЕАЛЬНЫЕ числа вхолодную, без приватного security-lab и без второго
движка. Числа, которые ревьюер воспроизводит, совпадают с заявленными.

Для аудита НОВОГО контракта нужен живой движок за портом (`SecurityLabAnalyzer`
или свой анализатор/Slither) — replay честно работает только на записанном.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.models import CodeLocation, Finding, Severity, SoliditySource

# parents[3] от app/adapters/analyzer/replay.py — корень репозитория.
_REPLAY_DIR = Path(__file__).resolve().parents[3] / "assets" / "eval" / "replay"


def finding_to_dict(f: Finding) -> dict[str, Any]:
    """Сериализовать `Finding` в JSON-совместимый словарь (стабильный формат фикстур)."""
    return {
        "detector": f.detector,
        "title": f.title,
        "location": {"file": f.location.file, "line": f.location.line},
        "snippet": f.snippet,
        "note": f.note,
        "severity": f.severity.value,
        "source": f.source,
    }


def finding_from_dict(d: dict[str, Any]) -> Finding:
    """Восстановить `Finding` из словаря фикстуры (обратна `finding_to_dict`)."""
    loc = d["location"]
    return Finding(
        detector=d["detector"],
        title=d["title"],
        location=CodeLocation(file=loc["file"], line=int(loc["line"])),
        snippet=d["snippet"],
        note=d["note"],
        severity=Severity(d["severity"]),
        source=d.get("source", "security-lab"),
    )


class ReplayAnalyzer:
    """Реализация порта `StaticAnalyzer` поверх записанных фикстур реального движка."""

    # Воспроизводим вывод security-lab дословно, включая атрибуцию источника, —
    # так eval-сравнение по ключам детекторов и провенанс совпадают с живым движком.
    name = "security-lab"

    def __init__(self, replay_dir: Path = _REPLAY_DIR) -> None:
        self._dir = replay_dir

    def analyze(self, source: SoliditySource) -> list[Finding]:
        fixture = self._dir / f"{source.path}.json"
        if not fixture.exists():
            raise FileNotFoundError(
                f"нет записи для {source.path} в {self._dir}. Replay работает только на "
                "записанных контрактах; для нового контракта нужен живой движок за портом "
                "(SecurityLabAnalyzer или свой анализатор)."
            )
        data = json.loads(fixture.read_text(encoding="utf-8"))
        return [finding_from_dict(d) for d in data]
