"""Юнит-тесты cross-model LLM-judge на фейковом судье (без сети)."""

from __future__ import annotations

from app.domain.audit import AuditFinding, Citation
from app.domain.llm import LLMResponse, Message, TokenUsage
from app.domain.models import CodeLocation, Severity
from app.eval.judge import grounding_rate, judge_grounding


class _FixedJudge:
    name = "judge"
    model = "judge-model"

    def __init__(self, answer: str, *, fail: bool = False) -> None:
        self._answer = answer
        self._fail = fail

    def generate(
        self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResponse:
        if self._fail:
            raise RuntimeError("judge down")
        return LLMResponse(
            text=self._answer,
            model="judge-model",
            provider="judge",
            usage=TokenUsage(1, 1),
            cost_usd=0.0,
            latency_ms=1.0,
        )


def _finding(*snippets: str) -> AuditFinding:
    return AuditFinding(
        detector="access",
        title="Missing access control",
        location=CodeLocation("V.sol", 1),
        snippet="code",
        severity=Severity.HIGH,
        rationale="attacker can seize ownership",
        fix="",
        citations=[Citation(source=f"doc{i}.md", snippet=s) for i, s in enumerate(snippets)],
    )


def test_judge_counts_supported_citations() -> None:
    verdict = judge_grounding(_finding("a", "b"), _FixedJudge("yes"), judged_by="ollama")
    assert verdict.supported == 2
    assert verdict.total == 2
    assert verdict.judged_by == "ollama"  # прозрачность модели-судьи


def test_judge_rejects_unsupported() -> None:
    verdict = judge_grounding(_finding("a", "b"), _FixedJudge("no"), judged_by="ollama")
    assert verdict.supported == 0


def test_judge_best_effort_on_error() -> None:
    # сбой судьи не должен засчитываться как поддержка (консервативно)
    verdict = judge_grounding(_finding("a"), _FixedJudge("", fail=True), judged_by="ollama")
    assert verdict.supported == 0


def test_grounding_rate_aggregates() -> None:
    verdicts = [
        judge_grounding(_finding("a", "b"), _FixedJudge("yes"), judged_by="ollama"),  # 2/2
        judge_grounding(_finding("c", "d"), _FixedJudge("no"), judged_by="ollama"),  # 0/2
    ]
    assert grounding_rate(verdicts) == 0.5


def test_grounding_rate_empty_is_one() -> None:
    assert grounding_rate([]) == 1.0
