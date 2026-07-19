"""Юнит-тесты eval-харнесса и отчёта на фейках (без сети/БД)."""

from __future__ import annotations

import json

from app.adapters.llm.router import LLMRouter
from app.domain.llm import LLMResponse, Message, TokenUsage
from app.domain.models import CodeLocation, Finding, Severity, SoliditySource
from app.domain.rag import Chunk, RetrievedChunk
from app.eval.corpus import EvalCase
from app.eval.harness import run_agent_eval, run_detector_eval
from app.eval.report import render_json, render_markdown
from app.rag.classify import KeywordClassifier

_AUDIT_JSON = '{"severity": "high", "rationale": "r", "citation_ids": [0], "fix": "f"}'


class _FakeCorpus:
    name = "fake"

    def __init__(self, cases: list[EvalCase]) -> None:
        self._cases = cases

    def cases(self) -> list[EvalCase]:
        return self._cases


class _FakeAnalyzer:
    name = "fake"

    def __init__(self, by_name: dict[str, list[str]]) -> None:
        self._by_name = by_name

    def analyze(self, source: SoliditySource) -> list[Finding]:
        return [
            Finding(
                detector=d,
                title=d,
                location=CodeLocation(source.path, 1),
                snippet="s",
                note="n",
                severity=Severity.LOW,
            )
            for d in self._by_name.get(source.path, [])
        ]


class _FakeEmbedder:
    name = "fake"
    dimension = 3

    def embed(self, texts: list[str]) -> list[list[float]]:
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


class _FakeProvider:
    def __init__(self, name: str, text: str, *, cost: float = 0.0) -> None:
        self.name = name
        self.model = f"{name}-m"
        self._text = text
        self._cost = cost

    def generate(
        self, messages: list[Message], *, temperature: float = 0.0, max_tokens: int | None = None
    ) -> LLMResponse:
        return LLMResponse(
            text=self._text,
            model=self.model,
            provider=self.name,
            usage=TokenUsage(1, 1),
            cost_usd=self._cost,
            latency_ms=1.0,
        )


def _case(name: str, code: str, expected: list[str]) -> EvalCase:
    return EvalCase(
        name=name,
        source=SoliditySource(name, code),
        vuln_class="x",
        expected_detectors=frozenset(expected),
    )


def _store() -> _FakeStore:
    return _FakeStore([Chunk(id="c0", source="patterns.md", content="body")])


def test_run_detector_eval_recall_over_covered() -> None:
    corpus = _FakeCorpus(
        [
            _case("A.sol", "a", ["reentrancy"]),  # analyzer fires reentrancy → hit
            _case("B.sol", "b", ["oracle"]),  # analyzer fires access → miss
            _case("C.sol", "c", []),  # не covered → вне знаменателя
        ]
    )
    analyzer = _FakeAnalyzer(
        {"A.sol": ["reentrancy", "danger"], "B.sol": ["access"], "C.sol": ["x"]}
    )
    result = run_detector_eval(corpus, analyzer)
    assert result.covered == 2
    assert result.confusion.tp == 1
    assert result.recall == 0.5


def test_run_agent_eval_with_judge() -> None:
    cases = [_case("A.sol", "contract A{}", ["access"])]
    router = LLMRouter({"gen": _FakeProvider("gen", _AUDIT_JSON, cost=0.02)}, default="gen")
    result = run_agent_eval(
        cases,
        _FakeAnalyzer({"A.sol": ["access"]}),
        _FakeEmbedder(),
        _store(),
        router,
        KeywordClassifier(),
        {"patterns.md"},
        judge=_FakeProvider("judge", "yes", cost=0.005),
        judge_label="ollama",
    )
    assert result.sample_size == 1
    assert result.findings == 1
    assert result.coverage == 1.0  # находка с цитатой
    assert result.faithfulness == 1.0  # source patterns.md ∈ known
    assert result.grounding == 1.0  # судья ответил yes
    assert result.judged_by == "ollama"
    assert abs(result.cost_usd - 0.02) < 1e-9
    assert abs(result.judge_cost_usd - 0.005) < 1e-9  # судья вне router.budget, учтён отдельно


def test_run_agent_eval_grounding_none_without_citations() -> None:
    router = LLMRouter({"gen": _FakeProvider("gen", _AUDIT_JSON)}, default="gen")
    result = run_agent_eval(
        [_case("A.sol", "contract A{}", ["access"])],
        _FakeAnalyzer({"A.sol": ["access"]}),
        _FakeEmbedder(),
        _FakeStore([]),  # пустой store → находки без цитат
        router,
        KeywordClassifier(),
        set(),
        judge=_FakeProvider("judge", "yes"),
        judge_label="ollama",
    )
    assert result.coverage == 0.0
    assert result.grounding is None  # нечего оценивать → не обманчивые 100%
    assert result.judged_by is None


def test_run_agent_eval_without_judge() -> None:
    router = LLMRouter({"gen": _FakeProvider("gen", _AUDIT_JSON)}, default="gen")
    result = run_agent_eval(
        [_case("A.sol", "contract A{}", ["access"])],
        _FakeAnalyzer({"A.sol": ["access"]}),
        _FakeEmbedder(),
        _store(),
        router,
        KeywordClassifier(),
        {"patterns.md"},
    )
    assert result.grounding is None
    assert result.judged_by is None


def test_render_markdown_and_json() -> None:
    corpus = _FakeCorpus([_case("A.sol", "a", ["reentrancy"]), _case("B.sol", "b", ["oracle"])])
    detector = run_detector_eval(
        corpus, _FakeAnalyzer({"A.sol": ["reentrancy"], "B.sol": ["access"]})
    )

    md = render_markdown(detector)
    assert "recall: 50%" in md
    assert "B.sol" in md  # промах показан

    payload = json.loads(render_json(detector))
    assert payload["detector"]["recall"] == 0.5
    assert len(payload["detector"]["cases"]) == 2
