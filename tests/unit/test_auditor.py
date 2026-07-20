"""Юнит-тесты цепочки аудитора на фейковых портах (без сети и БД)."""

from __future__ import annotations

from app.agent.auditor import _MAX_FINDINGS, audit_contract
from app.domain.llm import LLMResponse, Message, TokenUsage
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
