"""Интеграционный тест: реальный `recon.py` из security-lab.

Помечен `integration` и пропускается, если движок недоступен на диске
(например, на CI без security-lab). Проверяет, что мост действительно
поднимает настоящие детекторы и возвращает доменные находки.
"""

from __future__ import annotations

import pytest

from app.adapters.analyzer.security_lab import SecurityLabAnalyzer
from app.config import get_settings
from app.domain.models import Severity, SoliditySource

# Небольшой заведомо уязвимый контракт: приватный сеттер без модификатора доступа.
_VULNERABLE = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract Vault {
    uint256 public fee;

    // Привилегированный сеттер без onlyOwner — должен подсветиться access-детектором.
    function setFee(uint256 newFee) external {
        fee = newFee;
    }
}
"""


@pytest.mark.integration
def test_real_recon_flags_ungated_setter() -> None:
    toolkit = get_settings().recon_toolkit_path
    if not (toolkit / "recon.py").exists():
        pytest.skip(f"security-lab недоступен: {toolkit}")

    analyzer = SecurityLabAnalyzer.from_path(toolkit)
    findings = analyzer.analyze(SoliditySource(path="src/Vault.sol", code=_VULNERABLE))

    assert findings, "recon должен вернуть хотя бы одну находку на уязвимом контракте"
    assert all(f.source == "security-lab" for f in findings)
    # Пинним весь контракт целиком: реальный заголовок детектора → det_key → severity.
    assert any(
        f.detector == "access" and f.severity is Severity.HIGH for f in findings
    ), "ungated setFee должен дать access-находку с severity HIGH"
