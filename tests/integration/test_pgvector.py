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


@pytest.mark.integration
def test_replace_source_removes_orphans() -> None:
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    store = PgVectorStore(settings.database_url, dimension=_DIM, conn=conn)

    def count() -> int:
        row = conn.execute(
            "SELECT count(*) FROM chunks WHERE source = %s", ("test-pgv-src",)
        ).fetchone()
        return int(row[0]) if row else 0

    try:
        store.replace_source(
            "test-pgv-src",
            [
                Chunk(id=f"test-pgv-src#{i}", source="test-pgv-src", content=c)
                for i, c in enumerate("abc")
            ],
            [_one_hot(0), _one_hot(1), _one_hot(2)],
        )
        assert count() == 3
        # документ ужался до 1 чанка → orphans #1,#2 обязаны исчезнуть
        store.replace_source(
            "test-pgv-src",
            [Chunk(id="test-pgv-src#0", source="test-pgv-src", content="a2")],
            [_one_hot(0)],
        )
        assert count() == 1
    finally:
        conn.execute("DELETE FROM chunks WHERE id LIKE 'test-pgv-%'")
        store.close()


@pytest.mark.integration
def test_class_filter_narrows_to_class_and_general() -> None:
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    store = PgVectorStore(settings.database_url, dimension=_DIM, conn=conn)
    try:
        store.add(
            [
                Chunk(id="test-pgv-c1", source="d", content="a", metadata={"class": "reentrancy"}),
                Chunk(id="test-pgv-c2", source="d", content="b", metadata={"class": "oracle"}),
                Chunk(id="test-pgv-c3", source="d", content="c", metadata={"class": "general"}),
            ],
            [_one_hot(0), _one_hot(1), _one_hot(2)],
        )
        # запрос вектором c1: под фильтром reentrancy c1 совпадает, а c2 (oracle) отсечён классом.
        # Проверяем семантику фильтра, а не ранжирование — устойчиво к содержимому базы.
        by_c1 = {r.chunk.id for r in store.search(_one_hot(0), top_k=10, vuln_class="reentrancy")}
        assert "test-pgv-c1" in by_c1  # искомый класс совпал (косинус 1.0 к своему вектору)
        assert "test-pgv-c2" not in by_c1  # чужой класс не проходит фильтр
        # запрос вектором c3: general сопровождает любой искомый класс.
        by_c3 = {r.chunk.id for r in store.search(_one_hot(2), top_k=10, vuln_class="reentrancy")}
        assert "test-pgv-c3" in by_c3  # general включён вместе с искомым классом
    finally:
        conn.execute("DELETE FROM chunks WHERE id LIKE 'test-pgv-%'")
        store.close()
