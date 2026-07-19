"""Интеграция: PgVectorStore против живого Postgres (docker compose). Skip, если нет."""

from __future__ import annotations

import psycopg
import pytest

from app.adapters.vectorstore.pgvector_store import PgVectorStore
from app.config import get_settings
from app.domain.rag import Chunk

_DIM = 768


def _one_hot(index: int) -> list[float]:
    vec = [0.0] * _DIM
    vec[index] = 1.0
    return vec


@pytest.mark.integration
def test_add_and_cosine_search() -> None:
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    store = PgVectorStore(settings.database_url, dimension=_DIM, conn=conn)
    try:
        store.add(
            [
                Chunk(id="test-pgv-a", source="doc", content="reentrancy in withdraw"),
                Chunk(id="test-pgv-b", source="doc", content="spot price oracle"),
            ],
            [_one_hot(0), _one_hot(1)],
        )
        # запрос совпадает с вектором первого фрагмента → он и должен быть ближайшим
        results = store.search(_one_hot(0), top_k=1)
        assert len(results) == 1
        assert results[0].chunk.id == "test-pgv-a"
        assert results[0].chunk.content == "reentrancy in withdraw"
        assert results[0].score > 0.9  # косинус близок к 1

        # upsert по тому же id не плодит дубликат
        store.add([Chunk(id="test-pgv-a", source="doc", content="updated")], [_one_hot(0)])
        assert store.search(_one_hot(0), top_k=5)[0].chunk.content == "updated"
    finally:
        conn.execute("DELETE FROM chunks WHERE id LIKE 'test-pgv-%'")
        store.close()


@pytest.mark.integration
def test_full_text_search() -> None:
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    store = PgVectorStore(settings.database_url, dimension=_DIM, conn=conn)
    try:
        store.add(
            [
                Chunk(
                    id="test-pgv-t1",
                    source="d",
                    content="reentrancy external call before state write",
                ),
                Chunk(id="test-pgv-t2", source="d", content="spot price oracle manipulation"),
            ],
            [_one_hot(0), _one_hot(1)],
        )
        ids = [r.chunk.id for r in store.search_text("reentrancy external call", top_k=5)]
        assert "test-pgv-t1" in ids
        assert "test-pgv-t2" not in ids  # нет общих терминов с запросом
    finally:
        conn.execute("DELETE FROM chunks WHERE id LIKE 'test-pgv-%'")
        store.close()
