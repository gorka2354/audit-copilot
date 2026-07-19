"""Извлечение релевантных фрагментов корпуса по запросу (dense-поиск)."""

from __future__ import annotations

from app.domain.ports import Embedder, VectorStore
from app.domain.rag import RetrievedChunk


def retrieve(
    query: str, embedder: Embedder, store: VectorStore, *, top_k: int = 5
) -> list[RetrievedChunk]:
    query_vector = embedder.embed([query])[0]
    return store.search(query_vector, top_k=top_k)
