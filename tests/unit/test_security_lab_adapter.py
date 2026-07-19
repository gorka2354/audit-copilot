"""Юнит-тесты адаптера security-lab.

Движок `recon` подменяется фейком, поэтому тест проверяет ровно нашу логику
нормализации (сырой 5-кортеж → доменный `Finding`) и не зависит от диска.
"""

from __future__ import annotations

from app.adapters.analyzer.security_lab import SecurityLabAnalyzer
from app.domain.models import Severity, SoliditySource


class _FakeRecon:
    """Минимальный дубль recon: две находки разного приоритета."""

    @staticmethod
    def detect_all(text: str, rel: str) -> dict[str, list[tuple[str, int, str, str, int]]]:
        return {
            "ungated privileged setter": [
                (
                    rel,
                    12,
                    "  function setFee(uint x) external ",
                    "external + privileged, no auth ",
                    0,
                ),
            ],
            "divide before multiply": [
                (rel, 40, "a / b * c", "precision loss", 2),
            ],
        }

    @staticmethod
    def det_key(title: str) -> str:
        return {"ungated privileged setter": "access", "divide before multiply": "precision"}[title]


def _analyzer() -> SecurityLabAnalyzer:
    return SecurityLabAnalyzer(_FakeRecon())


def test_maps_priority_to_severity() -> None:
    findings = _analyzer().analyze(SoliditySource(path="src/Vault.sol", code="// ..."))
    by_detector = {f.detector: f for f in findings}
    assert by_detector["access"].severity is Severity.HIGH
    assert by_detector["precision"].severity is Severity.LOW


def test_preserves_location_and_trims_text() -> None:
    findings = _analyzer().analyze(SoliditySource(path="src/Vault.sol", code="// ..."))
    high = next(f for f in findings if f.detector == "access")
    assert high.title == "ungated privileged setter"
    assert str(high.location) == "src/Vault.sol:12"
    assert high.snippet == "function setFee(uint x) external"  # обрезаны пробелы
    assert high.note == "external + privileged, no auth"
    assert high.source == "security-lab"


def test_returns_one_finding_per_lead() -> None:
    findings = _analyzer().analyze(SoliditySource(path="src/Vault.sol", code="// ..."))
    assert len(findings) == 2
