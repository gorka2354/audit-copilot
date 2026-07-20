"""Юнит vendored-корпуса знаний: collect + ingest вхолодную, без security-lab (8a.4)."""

from __future__ import annotations

from app.domain.rag import Chunk, RetrievedChunk
from app.rag.classify import KeywordClassifier
from app.rag.ingest import collect_vendored_corpus, ingest


class _FakeEmbedder:
    name = "fake"
    dimension = 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]


class _RecordingStore:
    def __init__(self) -> None:
        self.sources: dict[str, list[Chunk]] = {}

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None: ...

    def close(self) -> None: ...

    def replace_source(
        self, source: str, chunks: list[Chunk], embeddings: list[list[float]]
    ) -> None:
        self.sources[source] = chunks

    def search(
        self, query_embedding: list[float], *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        return []

    def search_text(
        self, query: str, *, top_k: int = 5, vuln_class: str | None = None
    ) -> list[RetrievedChunk]:
        return []


def test_vendored_corpus_non_empty() -> None:
    docs = collect_vendored_corpus()
    assert len(docs) >= 9
    assert "corpus/reentrancy.md" in {s for s, _ in docs}


def test_ingest_vendored_corpus_cold() -> None:
    # ingest работает вхолодную (fake embedder/store, без security-lab и без сети).
    store = _RecordingStore()
    count = ingest(collect_vendored_corpus(), _FakeEmbedder(), store, KeywordClassifier())
    assert count > 0
    assert len(store.sources) >= 9
    # класс проставлен из содержимого паттерна.
    assert all(c.metadata["class"] == "reentrancy" for c in store.sources["corpus/reentrancy.md"])
