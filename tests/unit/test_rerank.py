"""Юнит-тесты LLM-реранка (best-effort: сбой/мусор → исходный порядок)."""

from __future__ import annotations

from app.domain.llm import LLMResponse, Message, TokenUsage
from app.domain.rag import Chunk, RetrievedChunk
from app.rag.rerank import llm_rerank


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


def _cands(n: int) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(chunk=Chunk(id=str(i), source="s", content=f"c{i}"), score=1.0)
        for i in range(n)
    ]


def test_rerank_reorders_by_llm() -> None:
    ranked = llm_rerank("q", _cands(4), _FakeLLM("[2, 0]"), top_k=2)
    assert [r.chunk.id for r in ranked] == ["2", "0"]


def test_rerank_fills_remaining_when_llm_returns_few() -> None:
    ranked = llm_rerank("q", _cands(4), _FakeLLM("[3]"), top_k=3)
    assert ranked[0].chunk.id == "3"
    assert len(ranked) == 3  # добито оставшимися


def test_rerank_falls_back_on_llm_error() -> None:
    ranked = llm_rerank("q", _cands(3), _FakeLLM("", fail=True), top_k=2)
    assert [r.chunk.id for r in ranked] == ["0", "1"]  # исходный порядок


def test_rerank_falls_back_on_garbage_output() -> None:
    ranked = llm_rerank("q", _cands(3), _FakeLLM("no json here"), top_k=2)
    assert [r.chunk.id for r in ranked] == ["0", "1"]
