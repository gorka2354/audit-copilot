"""Интеграция: guard против дрейфа разметки корпуса на реальном DeFiVulnLabs.

Ловит ситуацию из ревью Инкремента 5: размеченные файлы молча становятся
`unmapped` (выпадают из знаменателя recall), скрывая промахи детекторов.
Skip, если DeFiVulnLabs недоступен.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.eval.corpus import DeFiVulnLabsCorpus


@pytest.mark.integration
def test_known_labelled_files_stay_covered() -> None:
    corpus = DeFiVulnLabsCorpus.from_security_lab(get_settings().security_lab_path)
    cases = corpus.cases()
    if not cases:
        pytest.skip("DeFiVulnLabs недоступен — задай SECURITY_LAB_PATH")

    by_name = {c.name: c for c in cases}
    # эти файлы точно размечены в shadow.py — не должны выпадать в unmapped
    for name in ("Divmultiply.sol", "Returnfalse.sol", "return-break.sol"):
        assert name in by_name, f"{name} исчез из корпуса"
        assert by_name[name].is_covered, f"{name} стал unmapped — _BENCH разошёлся с shadow.py"

    covered = sum(1 for c in cases if c.is_covered)
    assert covered >= 34, f"покрытых кейсов {covered} < 34 — разметка потеряла классы"
