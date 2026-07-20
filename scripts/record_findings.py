"""One-time запись вывода реального security-lab в фикстуры для replay (8a.3).

Прогоняет `SecurityLabAnalyzer` на vendored-корпусе + примере-контракте и
сериализует нормализованные `Finding` в `assets/eval/replay/*.json`. Требует
`SECURITY_LAB_PATH` — нужен ОДИН раз, на запись. Результат коммитится, после чего
eval и demo воспроизводимы вхолодную через `ReplayAnalyzer`, без приватного движка.

Запуск: `uv run python scripts/record_findings.py`
"""

from __future__ import annotations

import json
from pathlib import Path

from app.adapters.analyzer.replay import _REPLAY_DIR, finding_to_dict, source_sha256
from app.adapters.analyzer.security_lab import SecurityLabAnalyzer
from app.config import get_settings
from app.domain.models import SoliditySource
from app.eval.corpus import _VENDORED_DIR

_EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "VulnerableVault.sol"
_CLEAN_DIR = Path(__file__).resolve().parents[1] / "assets" / "eval" / "clean"


def main() -> None:
    settings = get_settings()
    analyzer = SecurityLabAnalyzer.from_path(settings.recon_toolkit_path)
    _REPLAY_DIR.mkdir(parents=True, exist_ok=True)

    sources = sorted(_VENDORED_DIR.glob("*.sol")) + sorted(_CLEAN_DIR.glob("*.sol"))
    if _EXAMPLE.exists():
        sources.append(_EXAMPLE)

    total_findings = 0
    for path in sources:
        code = path.read_text(encoding="utf-8", errors="ignore")
        findings = analyzer.analyze(SoliditySource(path=path.name, code=code))
        payload = {
            "source_sha256": source_sha256(code),
            "engine": analyzer.name,
            "findings": [finding_to_dict(f) for f in findings],
        }
        (_REPLAY_DIR / f"{path.name}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        total_findings += len(findings)

    print(f"записано фикстур: {len(sources)} контрактов, {total_findings} находок → {_REPLAY_DIR}")


if __name__ == "__main__":
    main()
