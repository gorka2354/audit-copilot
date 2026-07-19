"""Извлечение релевантных фрагментов: dense, sparse и гибрид (RRF)."""

from __future__ import annotations

from app.domain.ports import Embedder, LLMProvider, VectorStore
from app.domain.rag import Chunk, RetrievedChunk
from app.rag.rerank import llm_rerank


def _embed_query(query: str, embedder: Embedder) -> list[float] | None:
    if not query.strip():
        return None
    vectors = embedder.embed([query])
    return vectors[0] if vectors else None


def retrieve(
    query: str, embedder: Embedder, store: VectorStore, *, top_k: int = 5
) -> list[RetrievedChunk]:
    """Плотный (dense) поиск: query → embed → cosine."""
    query_vector = _embed_query(query, embedder)
    if query_vector is None:
        return []
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
    query_vector = _embed_query(query, embedder)
    if query_vector is None:
        return []
    dense = store.search(query_vector, top_k=candidates)
    sparse = store.search_text(query, top_k=candidates)
    return reciprocal_rank_fusion([dense, sparse], top_k=top_k)


def retrieve_for_class(
    query: str,
    embedder: Embedder,
    store: VectorStore,
    *,
    vuln_class: str | None = None,
    top_k: int = 5,
    candidates: int = 20,
    reranker: LLMProvider | None = None,
) -> list[RetrievedChunk]:
    """Гибрид с фильтром по классу уязвимости + опциональный LLM-реранк (для агента)."""
    query_vector = _embed_query(query, embedder)
    if query_vector is None:
        return []
    dense = store.search(query_vector, top_k=candidates, vuln_class=vuln_class)
    sparse = store.search_text(query, top_k=candidates, vuln_class=vuln_class)
    fused = reciprocal_rank_fusion([dense, sparse], top_k=candidates)
    if reranker is not None:
        return llm_rerank(query, fused, reranker, top_k=top_k)
    return fused[:top_k]


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
