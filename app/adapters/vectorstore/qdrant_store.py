"""Адаптер векторного хранилища на Qdrant — второй бэкенд за портом `VectorStore`.

Существует, чтобы доказать, что порт не декоративный: тот же агент/RAG работает и на
Postgres/pgvector, и на Qdrant без единой правки выше адаптера.

Отличия от pgvector, скрытые портом:
- dense-поиск — родной cosine Qdrant;
- полнотекст — full-text payload index + `MatchText` (совпадение по словам, без
  BM25-ранжирования как в Postgres); для гибрида грубее, но контракт тот же;
- `Chunk.id` — произвольная строка, а point id в Qdrant обязан быть UUID/int, поэтому
  id детерминированно хешируется в UUID (`uuid5`), а оригинал лежит в payload;
- отсутствующий класс пишем как `general` при записи — эквивалент COALESCE в pgvector.
"""

from __future__ import annotations

import contextlib
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchText,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from app.domain.rag import Chunk, RetrievedChunk

_NAMESPACE = uuid.NAMESPACE_URL  # фиксированный namespace → стабильный uuid5 из Chunk.id


class QdrantStore:
    """`VectorStore` поверх Qdrant."""

    def __init__(self, url: str, *, dimension: int = 768, collection: str = "chunks") -> None:
        self._client = QdrantClient(url=url)
        self._collection = collection
        self._ensure_collection(dimension)

    def _ensure_collection(self, dimension: int) -> None:
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                self._collection,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
        # full-text индекс нужен для search_text (MatchText); повторное создание безопасно
        with contextlib.suppress(Exception):
            self._client.create_payload_index(
                self._collection, "content", field_schema=PayloadSchemaType.TEXT
            )

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        points = [
            self._point(chunk, embedding)
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]
        if points:
            self._client.upsert(self._collection, points=points)

    def replace_source(
        self, source: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        self._client.delete(
            self._collection,
            points_selector=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source))]
            ),
        )
        self.add(chunks, embeddings)

    def search(
        self, query_embedding: list[float], *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        response = self._client.query_points(
            self._collection,
            query=query_embedding,
            limit=top_k,
            query_filter=self._class_filter(vuln_class),
            with_payload=True,
        )
        return [self._to_result(point.payload, point.score) for point in response.points]

    def search_text(
        self, query: str, *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        must: list[Any] = [FieldCondition(key="content", match=MatchText(text=query))]
        class_filter = self._class_filter(vuln_class)
        if class_filter is not None:
            must.append(class_filter)
        points, _ = self._client.scroll(
            self._collection,
            scroll_filter=Filter(must=must),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        # full-text match не ранжирует — отдаём нейтральный score, RRF работает по рангу
        return [self._to_result(point.payload, 1.0) for point in points]

    def close(self) -> None:
        self._client.close()

    def _point(self, chunk: Chunk, embedding: list[float]) -> PointStruct:
        return PointStruct(
            id=str(uuid.uuid5(_NAMESPACE, chunk.id)),
            vector=embedding,
            payload={
                "chunk_id": chunk.id,
                "source": chunk.source,
                "content": chunk.content,
                "class": chunk.metadata.get("class", "general"),
                "metadata": chunk.metadata,
            },
        )

    @staticmethod
    def _class_filter(vuln_class: str | None) -> Filter | None:
        if vuln_class is None:
            return None
        return Filter(
            should=[
                FieldCondition(key="class", match=MatchValue(value=vuln_class)),
                FieldCondition(key="class", match=MatchValue(value="general")),
            ]
        )

    @staticmethod
    def _to_result(payload: dict[str, Any] | None, score: float | None) -> RetrievedChunk:
        data = payload or {}
        chunk = Chunk(
            id=str(data.get("chunk_id", "")),
            source=str(data.get("source", "")),
            content=str(data.get("content", "")),
            metadata=data.get("metadata") or {},
        )
        return RetrievedChunk(chunk=chunk, score=float(score) if score is not None else 0.0)
