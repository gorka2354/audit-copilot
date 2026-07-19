"""Интеграция: QdrantStore против живого Qdrant. Skip, если недоступен.

    docker compose --profile qdrant up -d qdrant
"""

from __future__ import annotations

import pytest

from app.adapters.vectorstore.qdrant_store import QdrantStore
from app.config import get_settings
from app.domain.rag import Chunk

_DIM = 8


def _one_hot(index: int) -> list[float]:
    vec = [0.0] * _DIM
    vec[index] = 1.0
    return vec


def _store() -> QdrantStore:
    try:
        return QdrantStore(get_settings().qdrant_url, dimension=_DIM, collection="test_chunks")
    except Exception:  # Qdrant недоступен (любой транспортный сбой)
        pytest.skip("Qdrant недоступен — docker compose --profile qdrant up -d qdrant")


@pytest.mark.integration
def test_add_and_dense_search() -> None:
    store = _store()
    try:
        store.replace_source(
            "d",
            [
                Chunk(id="q-a", source="d", content="reentrancy in withdraw"),
                Chunk(id="q-b", source="d", content="spot price oracle"),
            ],
            [_one_hot(0), _one_hot(1)],
        )
        results = store.search(_one_hot(0), top_k=1)
        assert results[0].chunk.id == "q-a"  # id восстановлен из payload (не UUID)
        assert results[0].chunk.content == "reentrancy in withdraw"
    finally:
        store.close()


@pytest.mark.integration
def test_class_filter_excludes_other_class() -> None:
    store = _store()
    try:
        store.replace_source(
            "d",
            [
                Chunk(id="q-c1", source="d", content="a", metadata={"class": "reentrancy"}),
                Chunk(id="q-c2", source="d", content="b", metadata={"class": "oracle"}),
            ],
            [_one_hot(0), _one_hot(1)],
        )
        ids = {r.chunk.id for r in store.search(_one_hot(0), top_k=10, vuln_class="reentrancy")}
        assert "q-c1" in ids
        assert "q-c2" not in ids  # чужой класс отсечён payload-фильтром
    finally:
        store.close()


@pytest.mark.integration
def test_full_text_search() -> None:
    store = _store()
    try:
        store.replace_source(
            "d",
            [
                Chunk(id="q-t1", source="d", content="reentrancy external call before write"),
                Chunk(id="q-t2", source="d", content="spot price oracle manipulation"),
            ],
            [_one_hot(0), _one_hot(1)],
        )
        ids = [r.chunk.id for r in store.search_text("reentrancy", top_k=5)]
        assert "q-t1" in ids
        assert "q-t2" not in ids
    finally:
        store.close()
