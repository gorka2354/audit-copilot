"""Юнит: роуты /audit и /search через TestClient с fake-портами (без lifespan/инфры)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_analyzer, get_embedder, get_router, get_store
from app.domain.llm import LLMError, LLMResponse, Message, TokenUsage
from app.domain.models import CodeLocation, Finding, Severity, SoliditySource
from app.domain.rag import Chunk, RetrievedChunk
from app.observability.budget import BudgetExceeded

_VALID_JSON = '{"severity": "high", "rationale": "drainable", "citation_ids": [0], "fix": "guard"}'


class _FakeAnalyzer:
    name = "fake"

    def __init__(self, findings: list[Finding]) -> None:
        self._findings = findings

    def analyze(self, source: SoliditySource) -> list[Finding]:
        return self._findings


class _FakeEmbedder:
    name = "fake"
    dimension = 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class _FakeStore:
    def __init__(self, chunks: list[Chunk]) -> None:
        self._chunks = chunks

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

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


class _FakeRouter:
    name = "router"
    model = "m"
    default = "anthropic"
    provider_names = ["anthropic"]

    def __init__(self, text: str = _VALID_JSON, *, exc: Exception | None = None) -> None:
        self._text = text
        self._exc = exc

    def generate(
        self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResponse:
        if self._exc is not None:
            raise self._exc
        return LLMResponse(
            text=self._text,
            model="m",
            provider="anthropic",
            usage=TokenUsage(1, 1),
            cost_usd=0.0,
            latency_ms=1.0,
        )


def _finding() -> Finding:
    return Finding(
        detector="access",
        title="Missing access control",
        location=CodeLocation("Vault.sol", 1),
        snippet="function setOwner() public {}",
        note="unprotected setter",
        severity=Severity.LOW,
    )


def _chunk() -> Chunk:
    return Chunk(id="c0", source="patterns.md", content="knowledge body")


def _client(
    *,
    analyzer: _FakeAnalyzer | None = None,
    store: _FakeStore | None = None,
    router: _FakeRouter | None = None,
) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_analyzer] = lambda: analyzer or _FakeAnalyzer([])
    app.dependency_overrides[get_embedder] = _FakeEmbedder
    app.dependency_overrides[get_store] = lambda: store or _FakeStore([])
    app.dependency_overrides[get_router] = lambda: router or _FakeRouter()
    return TestClient(app)  # без with → lifespan не запускается


def test_audit_returns_enriched_report() -> None:
    client = _client(
        analyzer=_FakeAnalyzer([_finding()]), store=_FakeStore([_chunk()]), router=_FakeRouter()
    )
    resp = client.post("/audit", json={"code": "contract Vault {}", "path": "Vault.sol"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["contract"] == "Vault.sol"
    assert body["high_count"] == 1
    assert len(body["findings"]) == 1
    finding = body["findings"][0]
    assert finding["detector"] == "access"  # провенанс детектора
    assert finding["severity"] == "high"  # LLM пересмотрел
    assert finding["file"] == "Vault.sol"
    assert finding["citations"][0]["source"] == "patterns.md"


def test_audit_rejects_empty_code() -> None:
    resp = _client().post("/audit", json={"code": ""})
    assert resp.status_code == 422  # pydantic min_length


def test_audit_budget_exceeded_returns_429() -> None:
    client = _client(
        analyzer=_FakeAnalyzer([_finding()]),
        store=_FakeStore([_chunk()]),
        router=_FakeRouter(exc=BudgetExceeded("исчерпан")),
    )
    resp = client.post("/audit", json={"code": "contract Vault {}"})
    assert resp.status_code == 429
    assert resp.json()["error"] == "budget_exceeded"


def test_audit_terminal_llm_error_returns_502() -> None:
    client = _client(
        analyzer=_FakeAnalyzer([_finding()]),
        store=_FakeStore([_chunk()]),
        router=_FakeRouter(exc=LLMError("unauthorized", retryable=False, provider="anthropic")),
    )
    resp = client.post("/audit", json={"code": "contract Vault {}"})
    assert resp.status_code == 502
    assert resp.json()["error"] == "llm_upstream"


def test_search_returns_results() -> None:
    resp = _client(store=_FakeStore([_chunk()])).post(
        "/search", json={"query": "reentrancy", "top_k": 3}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "reentrancy"
    assert len(body["results"]) == 1
    assert body["results"][0]["source"] == "patterns.md"
    assert body["results"][0]["chunk_id"] == "c0"


def test_search_rejects_empty_query() -> None:
    resp = _client().post("/search", json={"query": ""})
    assert resp.status_code == 422
