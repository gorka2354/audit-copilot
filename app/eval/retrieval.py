"""Метрики качества retrieval — чистые функции над ранжированным списком источников.

Оцениваем сам поиск (а не генерацию): для запроса с известным множеством релевантных
документов — nDCG@k (учёт позиции), MRR (первый релевантный) и recall@k (полнота топ-k).
Релевантность берётся из НЕЗАВИСИМОГО ручного gold-set (`retrieval_gold.py`), а не из
`metadata.class` — иначе метрика мерила бы самосогласованность классификатора, не поиск.
"""

from __future__ import annotations

from math import log2


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Доля релевантных документов, попавших в топ-k выдачи."""
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr(ranked: list[str], relevant: set[str]) -> float:
    """Reciprocal rank первого релевантного документа (0.0, если его нет в выдаче)."""
    for i, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Normalized DCG@k с бинарной релевантностью (0..1; 1.0 = идеальный ранг)."""
    dcg = sum(1.0 / log2(i + 1) for i, item in enumerate(ranked[:k], start=1) if item in relevant)
    ideal = sum(1.0 / log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0
