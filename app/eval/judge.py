"""Cross-model LLM-judge: поддерживает ли цитата находку (entailment-оценка).

Честность: судья ДОЛЖЕН быть другой моделью, чем генератор отчёта, иначе модель
хвалит собственные цитаты. Выбор cross-model и пометку модели-судьи (`judged_by`)
обеспечивает harness — здесь только сама оценка. Задача узкая (entailment
«поддерживает ли фрагмент утверждение»), а не «хорошо ли я справился».

Best-effort: сбой судьи или неоднозначный ответ → цитата НЕ засчитывается как
поддержанная (консервативно — метрика не завышается).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.audit import AuditFinding
from app.domain.llm import Message, Role
from app.domain.ports import LLMProvider


@dataclass(frozen=True, slots=True)
class GroundingVerdict:
    """Вердикт судьи по одной находке: сколько её цитат поддержаны."""

    detector: str
    supported: int
    total: int
    judged_by: str
    """Модель-судья — для прозрачности отчёта (и проверки, что судья ≠ генератор)."""

    cost_usd: float = 0.0
    """Стоимость вызовов судьи по этой находке — судья вне `router.budget`."""


def judge_grounding(
    finding: AuditFinding, judge: LLMProvider, *, judged_by: str
) -> GroundingVerdict:
    """Оценить судьёй, каждая ли цитата находки поддерживает её утверждение."""
    claim = f"{finding.title}. {finding.rationale}".strip()
    supported = 0
    cost = 0.0
    for citation in finding.citations:
        entailed, call_cost = _entails(claim, citation.snippet, judge)
        supported += int(entailed)
        cost += call_cost
    return GroundingVerdict(
        detector=finding.detector,
        supported=supported,
        total=len(finding.citations),
        judged_by=judged_by,
        cost_usd=cost,
    )


def grounding_rate(verdicts: list[GroundingVerdict]) -> float:
    """Доля цитат, признанных судьёй поддерживающими (по всем находкам)."""
    supported = sum(v.supported for v in verdicts)
    total = sum(v.total for v in verdicts)
    return supported / total if total else 1.0


def _entails(claim: str, evidence: str, judge: LLMProvider) -> tuple[bool, float]:
    prompt = (
        f"Claim: {claim}\n\nEvidence fragment: {evidence}\n\n"
        "Does the evidence fragment support the claim? Answer strictly 'yes' or 'no'."
    )
    try:
        response = judge.generate([Message(Role.USER, prompt)], max_tokens=10)
    except Exception:  # best-effort: сбой судьи не должен завышать метрику
        return False, 0.0
    return response.text.strip().lower().startswith("y"), response.cost_usd
