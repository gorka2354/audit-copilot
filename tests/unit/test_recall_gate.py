"""CI-гейт: метрики реального движка (через replay) не падают ниже базлайна (8c.2).

Вхолодную — `ReplayAnalyzer` + vendored DeFiVulnLabs, без security-lab/LLM/сети. Если
fixtures или корпус изменятся так, что recall просядет или движок зашумит сильнее, сборка
краснеет. Это превращает заявленную метрику из «утверждаю» в «гейчу»: обычный push с
регрессом recall до 40% больше не пройдёт зелёным.
"""

from __future__ import annotations

from app.adapters.analyzer.replay import ReplayAnalyzer
from app.eval.corpus import DeFiVulnLabsCorpus, load_clean_sources
from app.eval.harness import run_clean_eval, run_detector_eval


def test_detector_recall_gate() -> None:
    detector = run_detector_eval(DeFiVulnLabsCorpus.vendored(), ReplayAnalyzer())
    assert detector.covered == 34  # знаменатель зафиксирован
    assert detector.confusion.tp == 24  # baseline: 24 hit
    assert detector.recall >= 0.70  # covered recall не ниже 70%
    assert detector.corpus_recall >= 0.40  # корпусный recall не ниже 40%


def test_false_positive_rate_gate() -> None:
    # FP-rate на чистых контрактах не должен вырасти выше базлайна (движок не зашумел сильнее).
    clean = run_clean_eval(load_clean_sources(), ReplayAnalyzer())
    assert clean.total == 6
    assert clean.flagged <= 4  # baseline: 4/6 flagged — регресс в шумность не пройдёт
