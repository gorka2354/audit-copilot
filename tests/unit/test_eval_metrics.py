"""Юнит-тесты метрик eval на синтетике с известными значениями."""

from __future__ import annotations

from app.domain.audit import AuditFinding, Citation
from app.domain.models import CodeLocation, Severity
from app.eval.metrics import (
    Confusion,
    citation_coverage,
    confusion_from_labels,
    detector_confusion,
    structural_faithfulness,
)


def test_confusion_precision_recall_f1() -> None:
    c = Confusion(tp=8, fp=2, fn=2)
    assert c.precision == 0.8
    assert c.recall == 0.8
    assert abs(c.f1 - 0.8) < 1e-9


def test_confusion_zero_denominators_are_safe() -> None:
    c = Confusion(tp=0, fp=0, fn=0)
    assert c.precision == 0.0
    assert c.recall == 0.0
    assert c.f1 == 0.0


def test_detector_confusion_counts_hits_over_covered() -> None:
    results = [
        (frozenset({"reentrancy"}), frozenset({"reentrancy", "danger"})),  # hit
        (frozenset({"oracle"}), frozenset({"access"})),  # miss
        (frozenset(), frozenset({"whatever"})),  # не covered → вне знаменателя
    ]
    c = detector_confusion(results)
    assert c.tp == 1
    assert c.fn == 1
    assert c.recall == 0.5


def test_confusion_from_labels() -> None:
    c = confusion_from_labels([True, True, False, False], [True, False, True, False])
    assert (c.tp, c.fp, c.fn) == (1, 1, 1)


def _finding(*sources: str) -> AuditFinding:
    return AuditFinding(
        detector="d",
        title="t",
        location=CodeLocation("f.sol", 1),
        snippet="s",
        severity=Severity.LOW,
        rationale="r",
        fix="",
        citations=[Citation(source=s, snippet="x") for s in sources],
    )


def test_citation_coverage() -> None:
    findings = [_finding("a.md"), _finding(), _finding("b.md", "c.md")]
    assert abs(citation_coverage(findings) - 2 / 3) < 1e-9
    assert citation_coverage([]) == 0.0


def test_structural_faithfulness_flags_ungrounded_source() -> None:
    findings = [_finding("real.md", "fake.md"), _finding("real.md")]
    # 3 цитаты: real, fake, real → 2 источника из базы знаний из 3
    assert abs(structural_faithfulness(findings, {"real.md"}) - 2 / 3) < 1e-9


def test_faithfulness_is_one_without_citations() -> None:
    assert structural_faithfulness([_finding()], {"x"}) == 1.0
