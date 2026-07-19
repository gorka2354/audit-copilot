"""Адаптер векторного хранилища на Postgres + pgvector за портом `VectorStore`.

Синхронный psycopg3. Схема создаётся идемпотентно при инициализации; поиск —
по косинусной близости с HNSW-индексом. `Chunk.id` — ключ upsert.
"""

from __future__ import annotations

import json

import psycopg
from pgvector.psycopg import register_vector

from app.domain.rag import Chunk, RetrievedChunk

_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS chunks (
    id        text PRIMARY KEY,
    source    text NOT NULL,
    content   text NOT NULL,
    metadata  jsonb NOT NULL DEFAULT '{{}}',
    embedding vector({dim}) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);
"""

_UPSERT = """
INSERT INTO chunks (id, source, content, metadata, embedding)
VALUES (%s, %s, %s, %s, %s::vector)
ON CONFLICT (id) DO UPDATE SET
    source = EXCLUDED.source,
    content = EXCLUDED.content,
    metadata = EXCLUDED.metadata,
    embedding = EXCLUDED.embedding
"""

# `<=>` — косинусная дистанция (vector_cosine_ops); score = 1 - dist = близость.
_SEARCH = """
SELECT id, source, content, metadata, 1 - (embedding <=> %s::vector) AS score
FROM chunks
ORDER BY embedding <=> %s::vector
LIMIT %s
"""


class PgVectorStore:
    """`VectorStore` поверх Postgres/pgvector."""

    def __init__(
        self, dsn: str, *, dimension: int = 768, conn: psycopg.Connection | None = None
    ):
        self._dimension = dimension
        self._conn = conn or psycopg.connect(dsn, autocommit=True)
        register_vector(self._conn)
        self._conn.execute(_SCHEMA.format(dim=dimension))

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        with self._conn.cursor() as cur:
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                cur.execute(
                    _UPSERT,
                    (chunk.id, chunk.source, chunk.content, json.dumps(chunk.metadata), embedding),
                )

    def search(self, query_embedding: list[float], *, top_k: int = 5) -> list[RetrievedChunk]:
        rows = self._conn.execute(_SEARCH, (query_embedding, query_embedding, top_k)).fetchall()
        return [
            RetrievedChunk(
                chunk=Chunk(id=row[0], source=row[1], content=row[2], metadata=row[3]),
                score=float(row[4]),
            )
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()
