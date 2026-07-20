"""Юнит-тесты цепочки аудитора на фейковых портах (без сети и БД)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from app.agent.auditor import _MAX_FINDINGS, audit_contract
from app.domain.llm import LLMError, LLMResponse, Message, TokenUsage
from app.domain.models import CodeLocation, Finding, Severity, SoliditySource
from app.domain.rag import Chunk, RetrievedChunk
from app.rag.classify import KeywordClassifier

_KW = KeywordClassifier()


class _FakeAnalyzer:
    name = "fake"

    def __init__(self, findings: list[Finding]) -> None:
        self._findings = findings

    def analyze(self, source: SoliditySource) -> list[Finding]:
        return self._findings


class _FakeEmbedder:
    name = "fake"
    dimension = 3

    def __init__(self) -> None:
        self.embed_calls = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.embed_calls += 1
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeStore:
    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    def close(self) -> None: ...

    def replace_source(
        self, source: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None: ...

    def search(
        self, query_embedding: list[float], *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        return [RetrievedChunk(chunk=c, score=1.0) for c in self._chunks]

    def search_text(
        self, query: str, *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        return [RetrievedChunk(chunk=c, score=0.5) for c in self._chunks]


class _FakeLLM:
    name = "fake"
    model = "m"

    def __init__(self, text: str) -> None:
        self._text = text

    def generate(
        self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResponse:
        return LLMResponse(
            text=self._text,
            model="m",
            provider="fake",
            usage=TokenUsage(1, 1),
            cost_usd=0.0,
            latency_ms=1.0,
        )


def _finding(detector: str, title: str, line: int, severity: Severity) -> Finding:
    return Finding(
        detector=detector,
        title=title,
        location=CodeLocation("Vault.sol", line),
        snippet="function f() public {}",
        note="detector note",
        severity=severity,
    )


def _source() -> SoliditySource:
    return SoliditySource(path="Vault.sol", code="contract Vault {}")


def test_audit_contract_enriches_every_finding_with_provenance() -> None:
    findings = [
        _finding("access", "Missing access control", 1, Severity.LOW),
        _finding("spotoracle", "Spot price oracle", 2, Severity.MEDIUM),
    ]
    chunks = [Chunk(id="c0", source="patterns.md", content="knowledge body")]
    llm = _FakeLLM(
        '{"severity": "high", "rationale": "drainable", "citation_ids": [0], "fix": "fix"}'
    )

    report = audit_contract(
        _source(), _FakeAnalyzer(findings), _FakeEmbedder(), _FakeStore(chunks), llm, _KW
    )

    assert report.contract == "Vault.sol"
    assert len(report.findings) == 2
    assert report.high_count == 2  # LLM пересмотрел severity обеих находок
    # провенанс детектора сохранён, цитата привязана к реально переданному фрагменту
    assert [f.detector for f in report.findings] == ["access", "spotoracle"]
    assert [c.source for c in report.findings[0].citations] == ["patterns.md"]


def test_audit_contract_empty_recon_gives_empty_report() -> None:
    report = audit_contract(
        _source(), _FakeAnalyzer([]), _FakeEmbedder(), _FakeStore([]), _FakeLLM("{}"), _KW
    )
    assert report.findings == []
    assert report.high_count == 0


def test_audit_contract_survives_llm_garbage() -> None:
    findings = [_finding("access", "Missing access control", 1, Severity.MEDIUM)]
    chunks = [Chunk(id="c0", source="patterns.md", content="body")]

    report = audit_contract(
        _source(),
        _FakeAnalyzer(findings),
        _FakeEmbedder(),
        _FakeStore(chunks),
        _FakeLLM("no json"),
        _KW,
    )

    assert len(report.findings) == 1
    assert report.findings[0].severity is Severity.MEDIUM  # severity детектора сохранён
    assert report.findings[0].citations == []


def test_audit_contract_batches_embeddings() -> None:
    # 9.3: все query-эмбеддинги идут одним батч-вызовом, не по одному на находку
    findings = [_finding(f"d{i}", "t", i, Severity.LOW) for i in range(3)]
    embedder = _FakeEmbedder()
    audit_contract(
        _source(), _FakeAnalyzer(findings), embedder, _FakeStore([]), _FakeLLM("{}"), _KW
    )
    assert embedder.embed_calls == 1  # один батч на 3 находки, не 3 вызова


def test_audit_contract_caps_fan_out() -> None:
    # fan-out guard: аномально много находок обрезается до _MAX_FINDINGS (веер вызовов ограничен)
    many = [_finding(f"d{i}", "t", i, Severity.LOW) for i in range(_MAX_FINDINGS + 10)]
    chunks = [Chunk(id="c0", source="patterns.md", content="body")]
    report = audit_contract(
        _source(), _FakeAnalyzer(many), _FakeEmbedder(), _FakeStore(chunks), _FakeLLM("{}"), _KW
    )
    assert len(report.findings) == _MAX_FINDINGS


class _FailLLM:
    name = "f"
    model = "m"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def generate(
        self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResponse:
        raise self._exc


def test_audit_parallel_preserves_order() -> None:
    # 9.2: параллельное обогащение сохраняет порядок находок (не executor.map-как-попало)
    findings = [_finding(f"d{i}", "t", i, Severity.LOW) for i in range(5)]
    chunks = [Chunk(id="c0", source="patterns.md", content="body")]
    with ThreadPoolExecutor(max_workers=3) as ex:
        report = audit_contract(
            _source(),
            _FakeAnalyzer(findings),
            _FakeEmbedder(),
            _FakeStore(chunks),
            _FakeLLM("{}"),
            _KW,
            executor=ex,
        )
    assert [f.detector for f in report.findings] == [f"d{i}" for i in range(5)]


def test_audit_parallel_propagates_terminal_error() -> None:
    # терминальная ошибка (401) пробрасывается и в параллельном режиме, не маскируется
    findings = [_finding("access", "t", 1, Severity.LOW)]
    llm = _FailLLM(LLMError("401", retryable=False, provider="anthropic"))
    with ThreadPoolExecutor(max_workers=2) as ex, pytest.raises(LLMError):
        audit_contract(
            _source(),
            _FakeAnalyzer(findings),
            _FakeEmbedder(),
            _FakeStore([]),
            llm,
            _KW,
            executor=ex,
        )


def test_audit_parallel_marks_degraded_on_transient_failure() -> None:
    # транзиентный сбой LLM → находка НЕ теряется, помечена degraded (порядок и 1:1 целы)
    findings = [_finding("access", "t", 1, Severity.LOW)]
    llm = _FailLLM(LLMError("timeout", retryable=True, provider="ollama"))
    with ThreadPoolExecutor(max_workers=2) as ex:
        report = audit_contract(
            _source(),
            _FakeAnalyzer(findings),
            _FakeEmbedder(),
            _FakeStore([]),
            llm,
            _KW,
            executor=ex,
        )
    assert len(report.findings) == 1
    assert report.findings[0].degraded is True


class _BoomStore(_FakeStore):
    def search(
        self, query_embedding: list[float], *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        raise RuntimeError("db down")


def test_audit_sequential_survives_non_llm_failure() -> None:
    # паритет: сбой поиска (не synthesize) одной находки → degraded и в последовательном пути,
    # а не 500 на весь аудит (executor=None)
    findings = [_finding("access", "t", 1, Severity.LOW)]
    report = audit_contract(
        _source(), _FakeAnalyzer(findings), _FakeEmbedder(), _BoomStore([]), _FakeLLM("{}"), _KW
    )
    assert len(report.findings) == 1
    assert report.findings[0].degraded is True  # _guarded ловит сбой поиска, отчёт выживает
