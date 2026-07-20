"""LLM-синтез: обогащение статической находки severity/rationale/fix/цитатами.

Anti-hallucination контракт: находку уже установил детектор recon — LLM её не
оспаривает и не создаёт. Он лишь оценивает severity, объясняет риск и предлагает
фикс, опираясь на переданные фрагменты базы знаний. Цитаты проходят провенанс-
валидацию (`resolve_citations`): ссылка на фрагмент вне переданного контекста
молча отбрасывается, поэтому процитировать несуществующий источник модель не может.

Best-effort: при сбое LLM или неразборчивом ответе находка сохраняется с severity
детектора и без обогащения — сигнал не теряется никогда.
"""

from __future__ import annotations

import json

from app.domain.audit import AuditFinding, Citation
from app.domain.llm import LLMError, Message, Role
from app.domain.models import Finding, Severity
from app.domain.ports import LLMProvider
from app.domain.rag import RetrievedChunk
from app.observability.budget import BudgetExceeded

_CITATION_SNIPPET = 400  # символов из фрагмента, попадающих в цитату
_FRAGMENT_CHARS = 600  # символов фрагмента, показываемых модели
_MAX_TOKENS = 700

_SYSTEM = (
    "You are a smart-contract security auditor. A static detector has ALREADY "
    "flagged the finding below — do not dispute whether the issue exists. Your job "
    "is to rate its severity, explain the risk, and propose a concrete fix, grounded "
    "ONLY in the knowledge-base fragments provided. Never invent facts, CVEs, or "
    "sources. Cite supporting fragments by their index."
)


def synthesize_finding(
    finding: Finding, context: list[RetrievedChunk], llm: LLMProvider
) -> AuditFinding:
    """Обогатить один статический сигнал в `AuditFinding` через LLM (best-effort)."""
    messages = [
        Message(Role.SYSTEM, _SYSTEM),
        Message(Role.USER, _build_user_prompt(finding, context)),
    ]
    try:
        response = llm.generate(messages, max_tokens=_MAX_TOKENS)
    except BudgetExceeded:
        raise  # бюджет исчерпан — жёсткий стоп, не размениваем на молчаливый fallback
    except LLMError as exc:
        if not exc.retryable:
            raise  # терминальная ошибка (напр. 401) — не маскируем сломанный конфиг
        return _fallback(finding)  # транзиентная — обогащение опустим, находка выживает
    except Exception:  # прочее (парсинг вызова и т.п.) — best-effort fallback
        return _fallback(finding)

    parsed = _parse_enrichment(response.text)
    if parsed is None:
        return _fallback(finding)

    return AuditFinding(
        detector=finding.detector,
        title=finding.title,
        location=finding.location,
        snippet=finding.snippet,
        severity=_coerce_severity(parsed.get("severity"), finding.severity),
        rationale=_clean_text(parsed.get("rationale")) or finding.note,
        fix=_clean_text(parsed.get("fix")),
        citations=resolve_citations(parsed.get("citation_ids"), context),
        degraded=response.degraded,  # ответил резервный провайдер → помечаем находку
    )


def resolve_citations(raw_ids: object, context: list[RetrievedChunk]) -> list[Citation]:
    """Провенанс-валидатор: оставить только цитаты на реально переданные фрагменты.

    Индекс вне диапазона контекста, нецелочисленный или булев отбрасывается;
    дубликаты схлопываются. Так модель не может сослаться на источник, которого
    ей не давали, — цитата всегда воспроизводима из переданного `context`.
    """
    if not isinstance(raw_ids, list):
        return []
    citations: list[Citation] = []
    seen: set[int] = set()
    for i in raw_ids:
        if isinstance(i, bool) or not isinstance(i, int):
            continue
        if 0 <= i < len(context) and i not in seen:
            seen.add(i)
            chunk = context[i].chunk
            citations.append(
                Citation(source=chunk.source, snippet=chunk.content[:_CITATION_SNIPPET])
            )
    return citations


def _build_user_prompt(finding: Finding, context: list[RetrievedChunk]) -> str:
    if context:
        fragments = "\n\n".join(
            f"[{i}] ({c.chunk.source})\n{c.chunk.content[:_FRAGMENT_CHARS]}"
            for i, c in enumerate(context)
        )
    else:
        fragments = "(no fragments retrieved)"
    return (
        f"Detector: {finding.detector}\n"
        f"Vulnerability class: {finding.title}\n"
        f"Location: {finding.location}\n"
        f"Detector note: {finding.note}\n"
        f"Code snippet:\n{finding.snippet}\n\n"
        f"Knowledge-base fragments:\n{fragments}\n\n"
        "Respond with a single JSON object, no prose, of the form:\n"
        '{"severity": "high|medium|low|info", "rationale": "...", '
        '"citation_ids": [0, 2], "fix": "..."}\n'
        "Cite only genuinely relevant fragments; use [] if none apply."
    )


def _fallback(finding: Finding) -> AuditFinding:
    """Находка выживает без обогащения — severity детектора, note как обоснование.

    Обогащение не состоялось (LLM отказал или ответ неразборчив), поэтому degraded=True:
    находка есть, но качество суждения ниже — честно помечаем.
    """
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


def _parse_enrichment(text: str) -> dict[str, object] | None:
    """Достать первый валидный JSON-объект из ответа модели.

    `raw_decode` от каждой позиции `{` слева направо: так текст-обёртка или
    трейлинг-проза с фигурными скобками не ломает парсинг корректного JSON
    (жадный `\\{.*\\}` склеил бы объект с хвостом и потерял бы обогащение).
    """
    decoder = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = decoder.raw_decode(text[idx:])
        except ValueError:
            idx = text.find("{", idx + 1)
            continue
        return obj if isinstance(obj, dict) else None
    return None


def _coerce_severity(raw: object, fallback: Severity) -> Severity:
    if isinstance(raw, str):
        try:
            return Severity(raw.strip().lower())
        except ValueError:
            return fallback
    return fallback


def _clean_text(raw: object) -> str:
    return raw.strip() if isinstance(raw, str) else ""
