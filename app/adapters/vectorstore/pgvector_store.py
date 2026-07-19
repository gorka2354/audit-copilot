"""Адаптер векторного хранилища на Postgres + pgvector за портом `VectorStore`.

Синхронный psycopg3. Схема создаётся идемпотентно при инициализации; поиск —
dense (косинус + HNSW) и sparse (full-text + GIN). `Chunk.id` — ключ upsert;
`replace_source` даёт атомарную переиндексацию документа без orphans.
"""

from __future__ import annotations

import json
from typing import Any

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
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (content_tsv);
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
WHERE (%s::text IS NULL OR COALESCE(metadata->>'class', 'general') IN (%s, 'general'))
ORDER BY embedding <=> %s::vector
LIMIT %s
"""

# BM25-подобный полнотекстовый поиск через встроенный full-text Postgres.
_SEARCH_TEXT = """
SELECT id, source, content, metadata,
       ts_rank_cd(content_tsv, plainto_tsquery('english', %s)) AS score
FROM chunks
WHERE content_tsv @@ plainto_tsquery('english', %s)
  AND (%s::text IS NULL OR COALESCE(metadata->>'class', 'general') IN (%s, 'general'))
ORDER BY score DESC
LIMIT %s
"""


class PgVectorStore:
    """`VectorStore` поверх Postgres/pgvector."""

    def __init__(
        self, dsn: str, *, dimension: int = 768, conn: psycopg.Connection | None = None
    ):
        self._dimension = dimension
        own = conn is None
        self._conn = conn if conn is not None else psycopg.connect(dsn, autocommit=True)
        try:
            register_vector(self._conn)
            self._conn.execute(_SCHEMA.format(dim=dimension))
        except Exception:
            if own:  # чужое соединение закрывать не наша забота
                self._conn.close()
            raise

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        params = self._rows(chunks, embeddings)
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.executemany(_UPSERT, params)

    def replace_source(
        self, source: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        params = self._rows(chunks, embeddings)
        with self._conn.transaction(), self._conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE source = %s", (source,))
            if params:
                cur.executemany(_UPSERT, params)

    def search(
        self, query_embedding: list[float], *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        rows = self._conn.execute(
            _SEARCH, (query_embedding, vuln_class, vuln_class, query_embedding, top_k)
        ).fetchall()
        return self._to_results(rows)

    def search_text(
        self, query: str, *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        rows = self._conn.execute(
            _SEARCH_TEXT, (query, query, vuln_class, vuln_class, top_k)
        ).fetchall()
        return self._to_results(rows)

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _rows(
        chunks: list[Chunk], embeddings: list[list[float]]
    ) -> list[tuple[str, str, str, str, list[float]]]:
        return [
            (chunk.id, chunk.source, chunk.content, json.dumps(chunk.metadata), embedding)
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ]

    @staticmethod
    def _to_results(rows: list[tuple[Any, ...]]) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk=Chunk(id=row[0], source=row[1], content=row[2], metadata=row[3]),
                score=float(row[4]),
            )
            for row in rows
        ]
