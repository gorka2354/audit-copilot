"""Гейт целостности replay-фикстур: sha исходника в фикстуре == реальный `.sol`.

Закрывает medium из ревью Инкремента 8: `ReplayAnalyzer` ищет фикстуру по имени файла, поэтому
правка `.sol` без перезаписи фикстуры дала бы находки для старого кода, а eval/CI отрапортовали
бы неактуальные числа. Этот гейт краснеет раньше — привязывает воспроизводимость к
верифицируемости (fixture ↔ content), и гоняется в CI (unit).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.analyzer.replay import _REPLAY_DIR, source_sha256
from app.eval.corpus import _CLEAN_DIR, _VENDORED_DIR

_SOURCES = sorted(_VENDORED_DIR.glob("*.sol")) + sorted(_CLEAN_DIR.glob("*.sol"))


@pytest.mark.parametrize("sol", _SOURCES, ids=lambda p: p.name)
def test_fixture_matches_source(sol: Path) -> None:
    fixture = _REPLAY_DIR / f"{sol.name}.json"
    assert fixture.exists(), f"нет фикстуры для {sol.name} — прогони scripts/record_findings.py"
    data = json.loads(fixture.read_text(encoding="utf-8"))
    expected = source_sha256(sol.read_text(encoding="utf-8", errors="ignore"))
    assert data["source_sha256"] == expected, (
        f"{sol.name}: фикстура записана для другого исходника — перезапиши record_findings.py"
    )
