"""Юнит-тесты retrieve/hybrid/ingest с фейковыми Embedder/VectorStore."""

from __future__ import annotations

from app.domain.rag import Chunk, RetrievedChunk
from app.rag.ingest import ingest
from app.rag.retrieve import hybrid_retrieve, retrieve


class _FakeEmbedder:
    name = "fake"
    dimension = 3

    def __init__(self, *, empty: bool = False) -> None:
        self._empty = empty
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [] if self._empty else [[0.1, 0.2, 0.3] for _ in texts]


class _FakeStore:
    def __init__(self) -> None:
        self.replaced: dict[str, int] = {}

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    def replace_source(
        self, source: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        self.replaced[source] = len(chunks)

    def _hit(self) -> list[RetrievedChunk]:
        return [RetrievedChunk(chunk=Chunk(id="x", source="s", content="c"), score=1.0)]

    def search(
        self, query_embedding: list[float], *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        return self._hit()

    def search_text(
        self, query: str, *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        return self._hit()


def test_retrieve_empty_query_returns_empty_without_embedding() -> None:
    emb = _FakeEmbedder()
    assert retrieve("   ", emb, _FakeStore()) == []
    assert emb.calls == []  # пустой query не уходит в эмбеддер


def test_retrieve_handles_empty_embedding() -> None:
    assert retrieve("q", _FakeEmbedder(empty=True), _FakeStore()) == []


def test_hybrid_empty_query_returns_empty() -> None:
    assert hybrid_retrieve("", _FakeEmbedder(), _FakeStore()) == []


def test_ingest_replaces_each_source() -> None:
    store = _FakeStore()
    docs = [("a.md", "первый абзац\n\nвторой абзац"), ("b.md", "одиночный")]
    count = ingest(docs, _FakeEmbedder(), store)
    assert set(store.replaced) == {"a.md", "b.md"}
    assert count == sum(store.replaced.values())
