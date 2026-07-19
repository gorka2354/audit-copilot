"""Извлечение релевантных фрагментов: dense, sparse и гибрид (RRF)."""

from __future__ import annotations

from app.domain.ports import Embedder, VectorStore
from app.domain.rag import Chunk, RetrievedChunk


def retrieve(
    query: str, embedder: Embedder, store: VectorStore, *, top_k: int = 5
) -> list[RetrievedChunk]:
    """Плотный (dense) поиск: query → embed → cosine."""
    query_vector = embedder.embed([query])[0]
    return store.search(query_vector, top_k=top_k)


def hybrid_retrieve(
    query: str,
    embedder: Embedder,
    store: VectorStore,
    *,
    top_k: int = 5,
    candidates: int = 20,
) -> list[RetrievedChunk]:
    """Гибрид: dense (cosine) + sparse (BM25) → Reciprocal Rank Fusion.

    RRF сливает два ранжирования по рангам, а не по скорам — поэтому несравнимые
    величины (cosine-близость vs ts_rank) не требуют калибровки.
    """
    query_vector = embedder.embed([query])[0]
    dense = store.search(query_vector, top_k=candidates)
    sparse = store.search_text(query, top_k=candidates)
    return reciprocal_rank_fusion([dense, sparse], top_k=top_k)


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedChunk]], *, k: int = 60, top_k: int = 5
) -> list[RetrievedChunk]:
    """Объединить несколько ранжирований формулой RRF: score = Σ 1/(k + rank)."""
    fused: dict[str, tuple[float, Chunk]] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            prev_score, _ = fused.get(item.chunk.id, (0.0, item.chunk))
            fused[item.chunk.id] = (prev_score + 1.0 / (k + rank + 1), item.chunk)
    ordered = sorted(fused.values(), key=lambda pair: pair[0], reverse=True)
    return [RetrievedChunk(chunk=chunk, score=score) for score, chunk in ordered[:top_k]]
