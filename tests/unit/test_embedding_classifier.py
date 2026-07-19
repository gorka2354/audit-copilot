"""Юнит-тесты EmbeddingClassifier и build_classifier на управляемом fake-эмбеддере."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.rag.classify import KeywordClassifier, build_classifier
from app.rag.embedding_classifier import EmbeddingClassifier


class _KeywordishEmbedder:
    """Fake: тексты про reentrancy → [1,0], остальные → [0,1] — управляемый косинус."""

    name = "fake"
    dimension = 2

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] if "reentran" in t.lower() else [0.0, 1.0] for t in texts]


class _EmptyEmbedder:
    name = "fake"
    dimension = 2

    def embed(self, texts: list[str]) -> list[list[float]]:
        return []


def test_embedding_classifier_matches_semantic_prototype() -> None:
    clf = EmbeddingClassifier(_KeywordishEmbedder(), threshold=0.5)
    # reentrancy-прототип → [1,0]; запрос про reentrancy → [1,0]; косинус=1 → reentrancy
    assert clf.classify("an external reentrancy in withdraw") == "reentrancy"


def test_embedding_classifier_general_on_empty_embedding() -> None:
    assert EmbeddingClassifier(_EmptyEmbedder()).classify("some text") == "general"


def test_build_classifier_keyword() -> None:
    settings = Settings(classifier="keyword", _env_file=None)  # type: ignore[call-arg]
    assert isinstance(build_classifier(settings, _KeywordishEmbedder()), KeywordClassifier)


def test_build_classifier_embedding() -> None:
    settings = Settings(classifier="embedding", _env_file=None)  # type: ignore[call-arg]
    assert isinstance(build_classifier(settings, _KeywordishEmbedder()), EmbeddingClassifier)


def test_build_classifier_rejects_unknown() -> None:
    settings = Settings(classifier="magic", _env_file=None)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="неизвестный classifier"):
        build_classifier(settings, _KeywordishEmbedder())
