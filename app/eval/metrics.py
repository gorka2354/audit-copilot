"""Метрики качества eval — чистые функции над результатами прогона.

Уровни честно разделены:
- **detector recall** — поймал ли recon ожидаемый класс (пересечение expected ∩ fired);
- **citation coverage** — доля обогащённых находок хотя бы с одной цитатой;
- **структурная faithfulness** — доля цитат, чей источник реально есть в базе знаний.
  Провенанс by design даёт 1.0, поэтому метрика ловит регресс провенанса, а не хвалит модель.

Precision детекторов на минимальных репро сознательно НЕ считаем: «лишний» флаг там
не равен ложному срабатыванию (у контракта бывают и другие проблемы), так что честен
именно recall.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.audit import AuditFinding


@dataclass(frozen=True, slots=True)
class Confusion:
    """Счётчики матрицы ошибок с производными precision/recall/f1."""

    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def detector_confusion(results: list[tuple[frozenset[str], frozenset[str]]]) -> Confusion:
    """Confusion по covered-кейсам `(expected, fired)`; HIT = `expected ∩ fired ≠ ∅`.

    `tp` — кейсы, где сработал хотя бы один ожидаемый детектор; `fn` — где не сработал
    ни один. `fp` оставляем нулём осознанно (см. модульный docstring — precision на
    этом корпусе нечестен). Кейсы без ожидаемых детекторов не входят в знаменатель.
    """
    covered = [(expected, fired) for expected, fired in results if expected]
    tp = sum(1 for expected, fired in covered if expected & fired)
    return Confusion(tp=tp, fp=0, fn=len(covered) - tp)


def confusion_from_labels(predicted: list[bool], actual: list[bool]) -> Confusion:
    """Confusion из бинарных меток — для юнита/синтетики с известными TP/FP/FN."""
    pairs = list(zip(predicted, actual, strict=True))
    tp = sum(1 for p, a in pairs if p and a)
    fp = sum(1 for p, a in pairs if p and not a)
    fn = sum(1 for p, a in pairs if not p and a)
    return Confusion(tp=tp, fp=fp, fn=fn)


def citation_coverage(findings: list[AuditFinding]) -> float:
    """Доля находок хотя бы с одной цитатой."""
    if not findings:
        return 0.0
    return sum(1 for f in findings if f.citations) / len(findings)


def structural_faithfulness(findings: list[AuditFinding], known_sources: set[str]) -> float:
    """Доля цитат, чей источник реально присутствует в базе знаний.

    Провенанс гарантирует это конструктивно, поэтому честное значение — 1.0;
    отклонение вниз означает регресс провенанса. Если цитат нет — возвращаем 1.0
    (нечего нарушать; охват меряется отдельно через `citation_coverage`).
    """
    citations = [c for f in findings for c in f.citations]
    if not citations:
        return 1.0
    grounded = sum(1 for c in citations if c.source in known_sources)
    return grounded / len(citations)
