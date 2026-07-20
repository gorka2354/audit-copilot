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

import functools
import logging
from collections.abc import Callable
from concurrent.futures import Executor

from app.agent.synthesize import synthesize_finding
from app.domain.audit import AuditFinding, AuditReport
from app.domain.llm import LLMError
from app.domain.models import Finding, SoliditySource
from app.domain.ports import Classifier, Embedder, LLMProvider, StaticAnalyzer, VectorStore
from app.observability.budget import BudgetExceeded
from app.rag.classify import route_detector
from app.rag.retrieve import retrieve_for_class

_log = logging.getLogger("audit_copilot.auditor")

# Fan-out guard: каждая находка = embed + search + LLM-вызов. Аномально шумный контракт
# (или враждебный вход) мог бы прожечь бюджет и залить внешние сервисы — ограничиваем веер.
_MAX_FINDINGS = 50


def _finding_query(finding: Finding) -> str:
    """Текст запроса к базе знаний для находки."""
    return f"{finding.title}. {finding.note}"


def audit_contract(
    source: SoliditySource,
    analyzer: StaticAnalyzer,
    embedder: Embedder,
    store: VectorStore,
    llm: LLMProvider,
    classifier: Classifier,
    *,
    reranker: LLMProvider | None = None,
    top_k: int = 4,
    executor: Executor | None = None,
) -> AuditReport:
    """Провести аудит одного контракта и собрать обогащённый отчёт.

    Для каждой находки recon: определить класс уязвимости → достать релевантный
    контекст из базы знаний (гибрид с class-фильтром, опциональный реранк) →
    обогатить находку через LLM. Порядок и границы шагов задаёт код.

    Если передан `executor` — обогащение находок идёт параллельно (LLM-синтез
    сетевой, выигрыш реальный), с сохранением порядка; иначе последовательно
    (CLI/тесты). Эмбеддинги всегда батчатся до этого — их не параллелим. Обе
    ветки проходят через один `_guarded`: терминальные/бюджет пробрасываются,
    прочий сбой одной находки деградирует её, а не роняет весь отчёт.
    """
    findings = analyzer.analyze(source)
    _log.info("recon: %d finding(s) in %s", len(findings), source.path)
    if len(findings) > _MAX_FINDINGS:
        _log.warning(
            "recon дал %d находок в %s — обрезаю до %d (fan-out guard)",
            len(findings),
            source.path,
            _MAX_FINDINGS,
        )
        findings = findings[:_MAX_FINDINGS]

    # Батч-эмбеддинг всех query разом: эмбеддер удалённый и сериализует запросы,
    # поэтому один батч строго дешевле N одиночных вызовов на находку.
    query_vectors = embedder.embed([_finding_query(f) for f in findings]) if findings else []
    pairs = list(zip(findings, query_vectors, strict=True))

    def audit_one(finding: Finding, qv: list[float]) -> AuditFinding:
        return _audit_finding(
            finding, qv, embedder, store, llm, classifier, reranker=reranker, top_k=top_k
        )

    if executor is None:
        audited = [_guarded(f, functools.partial(audit_one, f, qv)) for f, qv in pairs]
    else:
        audited = _audit_parallel(executor, audit_one, pairs)

    report = AuditReport(contract=source.path, findings=audited)
    _log.info("report: %s → %d finding(s), %d high", source.path, len(audited), report.high_count)
    return report


def _guarded(finding: Finding, produce: Callable[[], AuditFinding]) -> AuditFinding:
    """Пофайндинговый guard: терминальные/бюджет пробрасываем, прочий сбой → degraded-находка.

    Синтез уже best-effort внутри, но эта обёртка ловит и сбои ДРУГИХ шагов находки
    (маршрутизация, поиск, реранк), чтобы одна проблемная находка не роняла весь отчёт —
    одинаково в последовательном и параллельном путях. Инвариант findings=detectors 1:1
    держится: возвращаем находку (обеднённую), а не пропускаем её.
    """
    try:
        return produce()
    except BudgetExceeded:
        raise  # бюджет — жёсткий стоп
    except LLMError as exc:
        if not exc.retryable:
            raise  # терминальная ошибка (401) — не маскируем сломанный конфиг degraded'ом
        _log.warning("обогащение %s сорвалось (%s) — degraded-находка", finding.detector, exc)
        return _bare_finding(finding)
    except Exception:  # noqa: BLE001 — одна находка не должна ронять весь отчёт
        _log.warning("обогащение %s сорвалось — degraded-находка", finding.detector)
        return _bare_finding(finding)


def _audit_parallel(
    executor: Executor,
    audit_one: Callable[[Finding, list[float]], AuditFinding],
    pairs: list[tuple[Finding, list[float]]],
) -> list[AuditFinding]:
    """Обогатить находки параллельно, СОХРАНИВ порядок; сбой одной не роняет весь батч.

    Собираем `fut.result()` в порядке `pairs` (не `as_completed`), поэтому порядок находок
    сохраняется. На терминальной/бюджетной ошибке отменяем ещё не начатые futures — чтобы
    не слать провайдеру обречённые запросы (напр. серию 401) после жёсткого стопа.
    """
    futures = [executor.submit(audit_one, f, qv) for f, qv in pairs]
    audited: list[AuditFinding] = []
    try:
        for (finding, _), fut in zip(pairs, futures, strict=True):
            audited.append(_guarded(finding, fut.result))
    except (BudgetExceeded, LLMError):
        for fut in futures:
            fut.cancel()  # отменит непошедшие в работу; работающие доиграют
        raise
    return audited


def _bare_finding(finding: Finding) -> AuditFinding:
    """Находка без обогащения (degraded): сбой одной не роняет весь отчёт."""
    return AuditFinding(
        detector=finding.detector,
        title=finding.title,
        location=finding.location,
        snippet=finding.snippet,
        severity=finding.severity,
        rationale=finding.note,
        fix="",
        citations=[],
        degraded=True,
    )


def _audit_finding(
    finding: Finding,
    query_vector: list[float],
    embedder: Embedder,
    store: VectorStore,
    llm: LLMProvider,
    classifier: Classifier,
    *,
    reranker: LLMProvider | None,
    top_k: int,
) -> AuditFinding:
    vuln_class = route_detector(classifier, finding.detector, finding.title, finding.note)
    query = _finding_query(finding)
    context = retrieve_for_class(
        query,
        embedder,
        store,
        vuln_class=vuln_class,
        top_k=top_k,
        reranker=reranker,
        query_vector=query_vector,
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
