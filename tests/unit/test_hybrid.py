"""Юнит-тесты Reciprocal Rank Fusion (гибридное слияние ранжирований)."""

from __future__ import annotations

from app.domain.rag import Chunk, RetrievedChunk
from app.rag.retrieve import reciprocal_rank_fusion


def _rc(chunk_id: str) -> RetrievedChunk:
    return RetrievedChunk(chunk=Chunk(id=chunk_id, source="s", content=chunk_id), score=1.0)


def test_rrf_rewards_agreement_across_rankings() -> None:
    # 'a' на топе в обоих ранжированиях → должен обойти 'b' и 'c' (каждый по разу)
    dense = [_rc("a"), _rc("b")]
    sparse = [_rc("a"), _rc("c")]
    fused = reciprocal_rank_fusion([dense, sparse], top_k=3)
    assert fused[0].chunk.id == "a"
    assert {r.chunk.id for r in fused} == {"a", "b", "c"}


def test_rrf_empty_inputs() -> None:
    assert reciprocal_rank_fusion([[], []]) == []


def test_rrf_respects_top_k() -> None:
    ranking = [_rc(str(i)) for i in range(10)]
    assert len(reciprocal_rank_fusion([ranking], top_k=3)) == 3


def test_rrf_higher_rank_wins_within_single_ranking() -> None:
    # при равном участии выше тот, кто стоял раньше (меньший rank → больший 1/(k+rank))
    fused = reciprocal_rank_fusion([[_rc("first"), _rc("second")]], top_k=2)
    assert [r.chunk.id for r in fused] == ["first", "second"]
