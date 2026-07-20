"""Юнит-тесты LLM-синтеза: обогащение находки и провенанс-валидация цитат."""

from __future__ import annotations

import pytest

from app.agent.synthesize import resolve_citations, synthesize_finding
from app.domain.llm import LLMError, LLMResponse, Message, TokenUsage
from app.domain.models import CodeLocation, Finding, Severity
from app.domain.rag import Chunk, RetrievedChunk
from app.observability.budget import BudgetExceeded


class _FakeLLM:
    name = "fake"
    model = "m"

    def __init__(self, text: str, *, fail: bool = False, degraded: bool = False) -> None:
        self._text = text
        self._fail = fail
        self._degraded = degraded

    def generate(
        self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResponse:
        if self._fail:
            raise RuntimeError("llm down")
        return LLMResponse(
            text=self._text,
            model="m",
            provider="fake",
            usage=TokenUsage(1, 1),
            cost_usd=0.0,
            latency_ms=1.0,
            degraded=self._degraded,
        )


def _finding() -> Finding:
    return Finding(
        detector="access",
        title="Missing access control",
        location=CodeLocation("Vault.sol", 42),
        snippet="function withdraw() public { ... }",
        note="public state-changing function without a guard",
        severity=Severity.LOW,
    )


def _context(n: int) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(chunk=Chunk(id=str(i), source=f"doc{i}.md", content=f"body {i}"), score=1.0)
        for i in range(n)
    ]


def test_synthesize_enriches_from_valid_json() -> None:
    llm = _FakeLLM(
        '{"severity": "high", "rationale": "attacker can drain", '
        '"citation_ids": [1], "fix": "add onlyOwner"}'
    )
    result = synthesize_finding(_finding(), _context(2), llm)

    assert result.detector == "access"  # провенанс детектора сохранён
    assert result.severity is Severity.HIGH  # LLM пересмотрел severity
    assert result.rationale == "attacker can drain"
    assert result.fix == "add onlyOwner"
    assert [c.source for c in result.citations] == ["doc1.md"]
    assert result.degraded is False  # основной провайдер → не деградировано


def test_synthesize_drops_out_of_context_citations() -> None:
    llm = _FakeLLM(
        '{"severity": "medium", "rationale": "r", "citation_ids": [0, 5, 99], "fix": "f"}'
    )
    result = synthesize_finding(_finding(), _context(2), llm)
    assert [c.source for c in result.citations] == ["doc0.md"]  # 5 и 99 вне контекста → отброшены


def test_synthesize_falls_back_on_llm_error() -> None:
    result = synthesize_finding(_finding(), _context(2), _FakeLLM("", fail=True))
    assert result.severity is Severity.LOW  # severity детектора
    assert result.rationale == "public state-changing function without a guard"
    assert result.fix == ""
    assert result.citations == []
    assert result.degraded is True  # обогащение не состоялось → честно помечено


def test_synthesize_marks_degraded_from_response() -> None:
    # ответ пришёл от резервного провайдера (degraded) → находка честно помечена
    llm = _FakeLLM(
        '{"severity": "high", "rationale": "r", "citation_ids": [], "fix": "f"}', degraded=True
    )
    assert synthesize_finding(_finding(), _context(1), llm).degraded is True


def test_synthesize_falls_back_on_garbage_output() -> None:
    result = synthesize_finding(_finding(), _context(2), _FakeLLM("sorry, no JSON here"))
    assert result.severity is Severity.LOW
    assert result.citations == []


def test_synthesize_keeps_detector_severity_on_unknown_severity() -> None:
    llm = _FakeLLM('{"severity": "critical", "rationale": "r", "citation_ids": [], "fix": "f"}')
    result = synthesize_finding(_finding(), _context(1), llm)
    assert result.severity is Severity.LOW  # "critical" не в enum → severity детектора
    assert result.rationale == "r"  # остальное обогащение принимается


def test_synthesize_parses_json_with_trailing_prose() -> None:
    # хвост с фигурными скобками после валидного JSON не должен ломать парсинг
    llm = _FakeLLM(
        '{"severity": "high", "rationale": "r", "citation_ids": [0], "fix": "f"} '
        "Note: consider {ReentrancyGuard}."
    )
    result = synthesize_finding(_finding(), _context(1), llm)
    assert result.severity is Severity.HIGH
    assert result.rationale == "r"
    assert [c.source for c in result.citations] == ["doc0.md"]


def test_resolve_citations_dedupes_and_rejects_non_indices() -> None:
    ctx = _context(3)
    # дубли схлопнуты; True (bool), строки, отрицательные и out-of-range отброшены
    cites = resolve_citations([0, 0, 2, -1, 7, True, "1"], ctx)
    assert [c.source for c in cites] == ["doc0.md", "doc2.md"]


def test_resolve_citations_handles_non_list() -> None:
    assert resolve_citations("not a list", _context(2)) == []
    assert resolve_citations(None, _context(2)) == []


class _RaisingLLM:
    name = "fake"
    model = "m"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(
        self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResponse:
        raise self._exc


def test_synthesize_propagates_budget_exceeded() -> None:
    # бюджет — жёсткий стоп, не должен глохнуть в fallback (иначе API не отдаст 429)
    with pytest.raises(BudgetExceeded):
        synthesize_finding(_finding(), _context(1), _RaisingLLM(BudgetExceeded("исчерпан")))


def test_synthesize_propagates_terminal_llm_error() -> None:
    # терминальная ошибка провайдера (напр. 401) не маскируется fallback'ом
    exc = LLMError("unauthorized", retryable=False, provider="anthropic")
    with pytest.raises(LLMError):
        synthesize_finding(_finding(), _context(1), _RaisingLLM(exc))


def test_synthesize_falls_back_on_retryable_llm_error() -> None:
    # транзиентная ошибка — обогащение опускаем, находка выживает с severity детектора
    exc = LLMError("temporary", retryable=True, provider="ollama")
    result = synthesize_finding(_finding(), _context(1), _RaisingLLM(exc))
    assert result.severity is Severity.LOW
    assert result.citations == []
