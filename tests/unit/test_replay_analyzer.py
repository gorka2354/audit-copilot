"""Юнит ReplayAnalyzer: round-trip Finding и чтение фикстур (без security-lab)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.analyzer.replay import (
    ReplayAnalyzer,
    finding_from_dict,
    finding_to_dict,
    source_sha256,
)
from app.domain.models import CodeLocation, Finding, Severity, SoliditySource
from app.domain.ports import StaticAnalyzer


def _finding() -> Finding:
    return Finding(
        detector="reentrancy",
        title="Reentrancy",
        location=CodeLocation(file="R.sol", line=12),
        snippet="msg.sender.call{value: a}()",
        note="external call before state write",
        severity=Severity.HIGH,
        source="security-lab",
    )


def test_finding_dict_roundtrip() -> None:
    f = _finding()
    assert finding_from_dict(finding_to_dict(f)) == f


def _fixture(code: str, findings: list[Finding]) -> str:
    return json.dumps(
        {
            "source_sha256": source_sha256(code),
            "engine": "security-lab",
            "findings": [finding_to_dict(f) for f in findings],
        }
    )


def test_replay_reads_recorded_findings(tmp_path: Path) -> None:
    code = "contract R {}"
    (tmp_path / "R.sol.json").write_text(_fixture(code, [_finding()]), encoding="utf-8")
    analyzer = ReplayAnalyzer(tmp_path)
    findings = analyzer.analyze(SoliditySource(path="R.sol", code=code))
    assert findings == [_finding()]
    assert analyzer.name == "security-lab"  # атрибуция дословно как у живого движка


def test_replay_rejects_stale_fixture(tmp_path: Path) -> None:
    # фикстура записана для одного исходника, анализируем другой → отказ (провенанс, не тихие числа)
    stale = _fixture("contract OLD {}", [_finding()])
    (tmp_path / "R.sol.json").write_text(stale, encoding="utf-8")
    analyzer = ReplayAnalyzer(tmp_path)
    with pytest.raises(ValueError, match="другого исходника"):
        analyzer.analyze(SoliditySource(path="R.sol", code="contract NEW {}"))


def test_replay_missing_fixture_raises(tmp_path: Path) -> None:
    analyzer = ReplayAnalyzer(tmp_path)
    with pytest.raises(FileNotFoundError, match="нет записи"):
        analyzer.analyze(SoliditySource(path="Unknown.sol", code=""))


def test_replay_satisfies_port() -> None:
    assert isinstance(ReplayAnalyzer(), StaticAnalyzer)
