"""Адаптер векторного хранилища на Postgres + pgvector за портом `VectorStore`.

Синхронный psycopg3. Схема создаётся идемпотентно при инициализации; поиск —
dense (косинус + HNSW) и sparse (full-text + GIN). `Chunk.id` — ключ upsert;
`replace_source` даёт атомарную переиндексацию документа без orphans.

Два режима соединения за единым внутренним `_connection()`:
- одиночное соединение (`dsn`/`conn`) — для скриптов и тестов;
- пул (`from_dsn_pool`) — для конкурентного доступа из API: sync-эндпоинты
  FastAPI работают в threadpool, поэтому каждый берёт свой коннекшн из пула
  и psycopg не ловит «another command is already in progress».
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg_pool import ConnectionPool

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


def _register_vector(conn: psycopg.Connection) -> None:
    """configure-callback пула: регистрирует тип `vector` на каждом соединении."""
    register_vector(conn)


class PgVectorStore:
    """`VectorStore` поверх Postgres/pgvector (одиночное соединение или пул)."""

    def __init__(
        self,
        dsn: str | None = None,
        *,
        dimension: int = 768,
        conn: psycopg.Connection | None = None,
        pool: ConnectionPool | None = None,
    ) -> None:
        provided = [n for n, v in (("dsn", dsn), ("conn", conn), ("pool", pool)) if v is not None]
        if len(provided) != 1:
            raise ValueError(
                f"нужен ровно один источник: dsn | conn | pool (задано: {provided or ['ничего']})"
            )
        self._dimension = dimension
        self._pool = pool
        self._owns_pool = False  # пул, созданный через from_dsn_pool, ставит True
        self._owns_conn = pool is None and conn is None  # владеем conn только если создали из dsn
        if pool is not None:
            self._conn = None
        elif conn is not None:
            self._conn = conn
        else:
            assert dsn is not None  # гарантировано проверкой источников выше
            self._conn = psycopg.connect(dsn, autocommit=True)
        try:
            self._init_schema()
        except Exception:
            if self._owns_conn and self._conn is not None:
                self._conn.close()
            raise

    @classmethod
    def from_dsn_pool(
        cls, dsn: str, *, dimension: int = 768, min_size: int = 1, max_size: int = 8
    ) -> PgVectorStore:
        """Собрать store поверх пула соединений — для конкурентного доступа (API)."""
        pool: ConnectionPool = ConnectionPool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            kwargs={"autocommit": True},
            configure=_register_vector,
            open=True,
        )
        try:
            store = cls(pool=pool, dimension=dimension)
        except Exception:
            pool.close()
            raise
        store._owns_pool = True
        return store

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        """Дать соединение: из пула (на время операции) либо постоянное."""
        if self._pool is not None:
            with self._pool.connection() as conn:
                yield conn
        else:
            assert self._conn is not None  # гарантировано конструктором в conn-режиме
            yield self._conn

    def _init_schema(self) -> None:
        with self._connection() as conn:
            if self._pool is None:
                register_vector(conn)  # для пула это делает configure на каждом соединении
            conn.execute(_SCHEMA.format(dim=self._dimension))

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        params = self._rows(chunks, embeddings)
        with self._connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.executemany(_UPSERT, params)

    def replace_source(
        self, source: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        params = self._rows(chunks, embeddings)
        with self._connection() as conn, conn.transaction(), conn.cursor() as cur:
            cur.execute("DELETE FROM chunks WHERE source = %s", (source,))
            if params:
                cur.executemany(_UPSERT, params)

    def search(
        self, query_embedding: list[float], *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        with self._connection() as conn:
            rows = conn.execute(
                _SEARCH, (query_embedding, vuln_class, vuln_class, query_embedding, top_k)
            ).fetchall()
        return self._to_results(rows)

    def search_text(
        self, query: str, *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        with self._connection() as conn:
            rows = conn.execute(
                _SEARCH_TEXT, (query, query, vuln_class, vuln_class, top_k)
            ).fetchall()
        return self._to_results(rows)

    def close(self) -> None:
        """Закрыть то, чем владеем: пул из `from_dsn_pool` или conn из `dsn`; чужое — нет."""
        if self._owns_pool and self._pool is not None:
            self._pool.close()
        elif self._owns_conn and self._conn is not None:
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
