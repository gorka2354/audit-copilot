"""Юнит метрик retrieval на синтетике с известным рангом (nDCG/MRR/recall@k)."""

from __future__ import annotations

from math import log2

from app.eval.retrieval import mrr, ndcg_at_k, recall_at_k


def test_recall_at_k() -> None:
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, {"a", "c"}, 4) == 1.0
    assert recall_at_k(ranked, {"a", "c"}, 2) == 0.5  # только "a" в топ-2
    assert recall_at_k(ranked, set(), 4) == 0.0


def test_mrr() -> None:
    assert mrr(["a", "b", "c"], {"b"}) == 0.5  # b на 2-й позиции → 1/2
    assert mrr(["a", "b", "c"], {"a"}) == 1.0
    assert mrr(["a", "b", "c"], {"z"}) == 0.0  # нет релевантных в выдаче


def test_ndcg_perfect_and_reversed() -> None:
    assert ndcg_at_k(["rel", "x", "y"], {"rel"}, 3) == 1.0  # идеальный ранг
    val = ndcg_at_k(["x", "y", "rel"], {"rel"}, 3)  # релевантный в конце
    assert abs(val - (1.0 / log2(4))) < 1e-9  # dcg = 1/log2(4), ideal = 1
    assert 0.0 < val < 1.0


def test_ndcg_empty_relevant() -> None:
    assert ndcg_at_k(["a", "b"], set(), 2) == 0.0
