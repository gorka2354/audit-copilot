"""Демо Инкремента 0.

Прогоняет статический анализатор security-lab на одном `.sol`-файле через
доменный порт и печатает нормализованные находки. Это первая вертикаль:
инфраструктурный движок → чистый домен → человекочитаемый вывод.

    uv run python scripts/demo_analyze.py path/to/Contract.sol
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from app.adapters.analyzer.security_lab import SecurityLabAnalyzer
from app.config import get_settings
from app.domain.models import Finding, Severity, SoliditySource

_MARKER = {Severity.HIGH: "[!]", Severity.MEDIUM: "[.]", Severity.LOW: "[ ]", Severity.INFO: "[i]"}
_ORDER = [Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]


def _render(findings: list[Finding], source_name: str) -> str:
    if not findings:
        return f"{source_name}: находок нет."
    counts = Counter(f.severity for f in findings)
    header = f"{source_name}: {len(findings)} находок  " + "  ".join(
        f"{_MARKER[s]}{counts[s]}" for s in _ORDER if counts[s]
    )
    lines = [header, "=" * len(header)]
    for sev in _ORDER:
        bucket = [f for f in findings if f.severity == sev]
        for f in bucket:
            lines.append(f"{_MARKER[sev]} {f.location}  ({f.detector})")
            lines.append(f"      {f.title}")
            if f.snippet:
                lines.append(f"      > {f.snippet}")
            if f.note:
                lines.append(f"        {f.note}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Статический аудит одного .sol через порт security-lab"
    )
    parser.add_argument("sol_file", type=Path, help="путь к .sol-файлу")
    args = parser.parse_args()

    settings = get_settings()
    analyzer = SecurityLabAnalyzer.from_path(settings.recon_toolkit_path)

    source = SoliditySource(path=args.sol_file.name, code=args.sol_file.read_text(encoding="utf-8"))
    findings = analyzer.analyze(source)

    print(_render(findings, args.sol_file.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
