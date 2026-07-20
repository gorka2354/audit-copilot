"""Юнит ReplayAnalyzer: round-trip Finding и чтение фикстур (без security-lab)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.adapters.analyzer.replay import ReplayAnalyzer, finding_from_dict, finding_to_dict
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


def test_replay_reads_recorded_findings(tmp_path: Path) -> None:
    (tmp_path / "R.sol.json").write_text(
        json.dumps([finding_to_dict(_finding())]), encoding="utf-8"
    )
    analyzer = ReplayAnalyzer(tmp_path)
    findings = analyzer.analyze(SoliditySource(path="R.sol", code="contract R {}"))
    assert findings == [_finding()]
    assert analyzer.name == "security-lab"  # атрибуция дословно как у живого движка


def test_replay_missing_fixture_raises(tmp_path: Path) -> None:
    analyzer = ReplayAnalyzer(tmp_path)
    with pytest.raises(FileNotFoundError, match="нет записи"):
        analyzer.analyze(SoliditySource(path="Unknown.sol", code=""))


def test_replay_satisfies_port() -> None:
    assert isinstance(ReplayAnalyzer(), StaticAnalyzer)
