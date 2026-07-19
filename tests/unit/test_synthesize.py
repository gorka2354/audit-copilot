"""Юнит-тесты LLM-синтеза: обогащение находки и провенанс-валидация цитат."""

from __future__ import annotations

from app.agent.synthesize import resolve_citations, synthesize_finding
from app.domain.llm import LLMResponse, Message, TokenUsage
from app.domain.models import CodeLocation, Finding, Severity
from app.domain.rag import Chunk, RetrievedChunk


class _FakeLLM:
    name = "fake"
    model = "m"

    def __init__(self, text: str, *, fail: bool = False) -> None:
        self._text = text
        self._fail = fail

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
