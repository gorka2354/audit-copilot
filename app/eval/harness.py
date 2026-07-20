"""Прогон eval: detector-level (offline, весь корпус) и agent-level (sample).

Два уровня раздельно и честно:
- `run_detector_eval` — recon на каждом кейсе, confusion по covered-классам. Offline,
  бесплатно, весь корпус.
- `run_agent_eval` — полный `audit_contract` на подвыборке: coverage, структурная
  faithfulness, cross-model grounding, стоимость и латентность. Дорого (LLM), поэтому
  подвыборка задаётся вызывающим.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.adapters.llm.router import LLMRouter
from app.agent.auditor import audit_contract
from app.domain.models import SoliditySource
from app.domain.ports import Classifier, Embedder, LLMProvider, StaticAnalyzer, VectorStore
from app.eval.corpus import EvalCase, EvalCorpus
from app.eval.judge import grounding_rate, judge_grounding
from app.eval.metrics import (
    Confusion,
    citation_coverage,
    detector_confusion,
    structural_faithfulness,
)


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    """Итог detector-level по одному кейсу."""

    name: str
    vuln_class: str
    expected: frozenset[str]
    fired: frozenset[str]

    @property
    def covered(self) -> bool:
        return bool(self.expected)

    @property
    def hit(self) -> bool:
        return bool(self.expected and self.expected & self.fired)


@dataclass(frozen=True, slots=True)
class DetectorEval:
    """Результат detector-level по всему корпусу."""

    corpus: str
    confusion: Confusion
    outcomes: list[CaseOutcome]

    @property
    def covered(self) -> int:
        return sum(1 for o in self.outcomes if o.covered)

    @property
    def blind_spots(self) -> int:
        """Классы, размеченные, но не покрытые ни одним детектором (движок их не умеет)."""
        return sum(1 for o in self.outcomes if not o.covered and o.vuln_class != "unmapped")

    @property
    def recall(self) -> float:
        """Recall по ПОКРЫТЫМ классам (самый мягкий знаменатель) — что движок реально ловит."""
        return self.confusion.recall

    @property
    def known_recall(self) -> float:
        """Recall по всем ИЗВЕСТНЫМ классам (covered + blind-spots).

        Blind-spot — реальный класс уязвимости, который движок не детектит; с точки
        зрения пользователя это промах, поэтому честно включить его в знаменатель.
        """
        denom = self.covered + self.blind_spots
        return self.confusion.tp / denom if denom else 0.0

    @property
    def corpus_recall(self) -> float:
        """Recall по всему корпусу репро — самый строгий знаменатель."""
        return self.confusion.tp / len(self.outcomes) if self.outcomes else 0.0


@dataclass(frozen=True, slots=True)
class AgentEval:
    """Результат agent-level по подвыборке."""

    sample_size: int
    findings: int
    coverage: float
    faithfulness: float
    grounding: float | None
    judged_by: str | None
    grounding_supported: int
    grounding_total: int
    cost_usd: float
    judge_cost_usd: float
    avg_latency_ms: float


@dataclass(frozen=True, slots=True)
class CleanEval:
    """FP-оценка на заведомо чистых контрактах: любое срабатывание = ложное."""

    total: int
    flagged: int
    total_findings: int

    @property
    def flagged_fraction(self) -> float:
        return self.flagged / self.total if self.total else 0.0

    @property
    def avg_fp(self) -> float:
        return self.total_findings / self.total if self.total else 0.0


def run_detector_eval(corpus: EvalCorpus, analyzer: StaticAnalyzer) -> DetectorEval:
    """Прогнать статические детекторы на каждом кейсе корпуса и собрать confusion."""
    outcomes: list[CaseOutcome] = []
    for case in corpus.cases():
        fired = frozenset(f.detector for f in analyzer.analyze(case.source))
        outcomes.append(
            CaseOutcome(
                name=case.name,
                vuln_class=case.vuln_class,
                expected=case.expected_detectors,
                fired=fired,
            )
        )
    confusion = detector_confusion([(o.expected, o.fired) for o in outcomes])
    return DetectorEval(corpus=corpus.name, confusion=confusion, outcomes=outcomes)


def run_clean_eval(clean_sources: list[SoliditySource], analyzer: StaticAnalyzer) -> CleanEval:
    """FP-rate: прогнать детекторы на заведомо чистых контрактах (любое срабатывание ложное)."""
    counts = [len(analyzer.analyze(s)) for s in clean_sources]
    return CleanEval(
        total=len(counts),
        flagged=sum(1 for c in counts if c > 0),
        total_findings=sum(counts),
    )


def run_agent_eval(
    cases: list[EvalCase],
    analyzer: StaticAnalyzer,
    embedder: Embedder,
    store: VectorStore,
    router: LLMRouter,
    classifier: Classifier,
    known_sources: set[str],
    *,
    reranker: LLMProvider | None = None,
    top_k: int = 4,
    judge: LLMProvider | None = None,
    judge_label: str | None = None,
) -> AgentEval:
    """Полный аудит на подвыборке: охват/faithfulness/grounding/стоимость/латентность."""
    findings = []
    latencies: list[float] = []
    cost_before = router.budget.spent_usd

    for case in cases:
        start = time.perf_counter()
        report = audit_contract(
            case.source,
            analyzer,
            embedder,
            store,
            router,
            classifier,
            reranker=reranker,
            top_k=top_k,
        )
        latencies.append((time.perf_counter() - start) * 1000)
        findings.extend(report.findings)

    grounding: float | None = None
    judged_by: str | None = None
    judge_cost = 0.0
    supported = 0
    total_cited = 0
    if judge is not None and judge_label is not None:
        verdicts = [judge_grounding(f, judge, judged_by=judge_label) for f in findings]
        judge_cost = sum(v.cost_usd for v in verdicts)
        supported = sum(v.supported for v in verdicts)
        total_cited = sum(v.total for v in verdicts)
        # grounding имеет смысл только если было что оценивать (иначе rate вернул бы
        # обманчивые 1.0 при нуле цитат — см. ревью Инкремента 5)
        if total_cited > 0:
            grounding = grounding_rate(verdicts)
            judged_by = judge_label

    return AgentEval(
        sample_size=len(cases),
        findings=len(findings),
        coverage=citation_coverage(findings),
        faithfulness=structural_faithfulness(findings, known_sources),
        grounding=grounding,
        judged_by=judged_by,
        grounding_supported=supported,
        grounding_total=total_cited,
        cost_usd=router.budget.spent_usd - cost_before,
        judge_cost_usd=judge_cost,
        avg_latency_ms=sum(latencies) / len(latencies) if latencies else 0.0,
    )
