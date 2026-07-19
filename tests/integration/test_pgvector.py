"""Интеграция: PgVectorStore против живого Postgres (docker compose). Skip, если нет."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

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

    store = PgVectorStore(conn=conn, dimension=_DIM)
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

    store = PgVectorStore(conn=conn, dimension=_DIM)
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

    store = PgVectorStore(conn=conn, dimension=_DIM)

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

    store = PgVectorStore(conn=conn, dimension=_DIM)
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


@pytest.mark.integration
def test_class_filter_applies_to_full_text_search() -> None:
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    store = PgVectorStore(conn=conn, dimension=_DIM)
    try:
        # одинаковый текст, разные классы — изолирует фильтр от текстового ранга (sparse-ветка)
        store.add(
            [
                Chunk(
                    id="test-pgv-ft1",
                    source="d",
                    content="reentrancy external call guard",
                    metadata={"class": "reentrancy"},
                ),
                Chunk(
                    id="test-pgv-ft2",
                    source="d",
                    content="reentrancy external call guard",
                    metadata={"class": "oracle"},
                ),
            ],
            [_one_hot(0), _one_hot(1)],
        )
        ids = {
            r.chunk.id
            for r in store.search_text(
                "reentrancy external call", top_k=10, vuln_class="reentrancy"
            )
        }
        assert "test-pgv-ft1" in ids  # текст совпал и класс совпал
        assert "test-pgv-ft2" not in ids  # тот же текст, но класс oracle — отсечён фильтром
    finally:
        conn.execute("DELETE FROM chunks WHERE id LIKE 'test-pgv-%'")
        store.close()


@pytest.mark.integration
def test_class_filter_treats_missing_class_as_general() -> None:
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    store = PgVectorStore(conn=conn, dimension=_DIM)
    try:
        # чанк без metadata.class (напр. проиндексирован до class-стампа) не должен выпадать
        store.add([Chunk(id="test-pgv-nc", source="d", content="x")], [_one_hot(0)])
        ids = {r.chunk.id for r in store.search(_one_hot(0), top_k=10, vuln_class="reentrancy")}
        assert "test-pgv-nc" in ids  # отсутствие класса трактуется как general → проходит фильтр
    finally:
        conn.execute("DELETE FROM chunks WHERE id LIKE 'test-pgv-%'")
        store.close()


def _cleanup(dsn: str, like: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DELETE FROM chunks WHERE id LIKE %s", (like,))


@pytest.mark.integration
def test_pool_mode_add_and_search() -> None:
    settings = get_settings()
    try:
        store = PgVectorStore.from_dsn_pool(settings.database_url, dimension=_DIM, max_size=2)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    try:
        store.add([Chunk(id="test-pgv-pool", source="d", content="pooled")], [_one_hot(0)])
        results = store.search(_one_hot(0), top_k=1)
        assert results[0].chunk.id == "test-pgv-pool"
        assert results[0].chunk.content == "pooled"
    finally:
        _cleanup(settings.database_url, "test-pgv-pool%")
        store.close()


@pytest.mark.integration
def test_pool_handles_concurrent_search() -> None:
    settings = get_settings()
    try:
        store = PgVectorStore.from_dsn_pool(settings.database_url, dimension=_DIM, max_size=4)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    try:
        store.add([Chunk(id="test-pgv-pool", source="d", content="pooled")], [_one_hot(0)])
        # 8 одновременных запросов через 4 потока: с одним соединением psycopg упал бы
        # с «another command is already in progress»; пул выдаёт каждому свой коннекшн
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(store.search, _one_hot(0), top_k=1) for _ in range(8)]
            results = [f.result() for f in as_completed(futures)]
        assert len(results) == 8
        assert all(r and r[0].chunk.id == "test-pgv-pool" for r in results)
    finally:
        _cleanup(settings.database_url, "test-pgv-pool%")
        store.close()


@pytest.mark.integration
def test_pool_bootstraps_vector_extension_on_fresh_db() -> None:
    settings = get_settings()
    try:
        admin = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    fresh_dsn = settings.database_url.rsplit("/", 1)[0] + "/audit_fresh_test"
    try:
        admin.execute("DROP DATABASE IF EXISTS audit_fresh_test")
        admin.execute("CREATE DATABASE audit_fresh_test")
        # свежая БД без расширения vector — from_dsn_pool обязан сам его создать,
        # иначе register_vector падает и пул виснет на PoolTimeout (регресс high-бага)
        store = PgVectorStore.from_dsn_pool(fresh_dsn, dimension=_DIM, max_size=2)
        try:
            store.add([Chunk(id="fresh", source="s", content="c")], [_one_hot(0)])
            assert store.search(_one_hot(0), top_k=1)[0].chunk.id == "fresh"
        finally:
            store.close()
    finally:
        admin.execute("DROP DATABASE IF EXISTS audit_fresh_test")
        admin.close()
