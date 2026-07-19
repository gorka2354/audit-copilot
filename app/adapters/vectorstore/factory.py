"""Композиционный корень vectorstore: выбор бэкенда по настройкам.

Демонстрация гексагона: `VECTOR_STORE=pgvector|qdrant` переключает весь стек на
другой бэкенд без единой правки в агенте, RAG или API — они знают только порт
`VectorStore`.
"""

from __future__ import annotations

from app.adapters.vectorstore.pgvector_store import PgVectorStore
from app.adapters.vectorstore.qdrant_store import QdrantStore
from app.config import Settings
from app.domain.ports import VectorStore

_KNOWN_BACKENDS = frozenset({"pgvector", "qdrant"})


def build_store(settings: Settings) -> VectorStore:
    """Собрать хранилище по `settings.vector_store` (`pgvector` | `qdrant`)."""
    backend = settings.vector_store
    if backend == "qdrant":
        return QdrantStore(settings.qdrant_url, dimension=settings.embed_dimension)
    if backend == "pgvector":
        return PgVectorStore.from_dsn_pool(
            settings.database_url, dimension=settings.embed_dimension
        )
    raise ValueError(f"неизвестный vector_store '{backend}'; допустимо: {sorted(_KNOWN_BACKENDS)}")
