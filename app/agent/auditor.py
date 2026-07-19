"""Аудитор: code-driven цепочка recon → RAG(class) → LLM-синтез → отчёт.

Цепочка детерминирована и управляется кодом, а не моделью: множество находок
задаёт статический анализатор (recon), маршрутизацию каждой находки в нужный
класс базы знаний и порядок шагов — этот модуль, а LLM вызывается точечно лишь
для обогащения. Поэтому каждый пункт отчёта прослеживается до детектора и до
проверенных цитат — модель не может ни выдумать находку, ни подменить провенанс.

Учёт бюджета не дублируется здесь: если `llm` — это `LLMRouter`, он уже считает
токены и стоимость через `BudgetTracker`. Наблюдаемость цепочки — через logging.
"""

from __future__ import annotations

import logging

from app.agent.synthesize import synthesize_finding
from app.domain.audit import AuditFinding, AuditReport
from app.domain.models import Finding, SoliditySource
from app.domain.ports import Embedder, LLMProvider, StaticAnalyzer, VectorStore
from app.rag.classify import class_for_detector
from app.rag.retrieve import retrieve_for_class

_log = logging.getLogger("audit_copilot.auditor")


def audit_contract(
    source: SoliditySource,
    analyzer: StaticAnalyzer,
    embedder: Embedder,
    store: VectorStore,
    llm: LLMProvider,
    *,
    reranker: LLMProvider | None = None,
    top_k: int = 4,
) -> AuditReport:
    """Провести аудит одного контракта и собрать обогащённый отчёт.

    Для каждой находки recon: определить класс уязвимости → достать релевантный
    контекст из базы знаний (гибрид с class-фильтром, опциональный реранк) →
    обогатить находку через LLM. Порядок и границы шагов задаёт код.
    """
    findings = analyzer.analyze(source)
    _log.info("recon: %d finding(s) in %s", len(findings), source.path)

    audited = [
        _audit_finding(finding, embedder, store, llm, reranker=reranker, top_k=top_k)
        for finding in findings
    ]
    report = AuditReport(contract=source.path, findings=audited)
    _log.info("report: %s → %d finding(s), %d high", source.path, len(audited), report.high_count)
    return report


def _audit_finding(
    finding: Finding,
    embedder: Embedder,
    store: VectorStore,
    llm: LLMProvider,
    *,
    reranker: LLMProvider | None,
    top_k: int,
) -> AuditFinding:
    vuln_class = class_for_detector(finding.detector, finding.title, finding.note)
    query = f"{finding.title}. {finding.note}"
    context = retrieve_for_class(
        query, embedder, store, vuln_class=vuln_class, top_k=top_k, reranker=reranker
    )
    _log.info(
        "finding %s@%s → class=%s, %d fragment(s)",
        finding.detector,
        finding.location,
        vuln_class or "any",
        len(context),
    )
    enriched = synthesize_finding(finding, context, llm)
    _log.info(
        "enriched %s@%s → %s (%d citation(s))",
        enriched.detector,
        enriched.location,
        enriched.severity,
        len(enriched.citations),
    )
    return enriched
