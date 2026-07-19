"""Юнит-тесты Ollama-эмбеддера с мок-транспортом httpx (без сети)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from app.adapters.embedder.ollama_embed import EmbedderError, OllamaEmbedder


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_returns_vectors_in_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    emb = OllamaEmbedder("m", client=_client(handler), dimension=2)
    assert emb.embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_empty_input_skips_network() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"embeddings": []})

    emb = OllamaEmbedder("m", client=_client(handler))
    assert emb.embed([]) == []
    assert not calls  # пустой вход не дёргает сеть


def test_count_mismatch_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1]]})  # 1 вектор на 2 текста

    emb = OllamaEmbedder("m", client=_client(handler))
    with pytest.raises(EmbedderError):
        emb.embed(["a", "b"])


def test_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    emb = OllamaEmbedder("m", client=_client(handler))
    with pytest.raises(EmbedderError):
        emb.embed(["a"])
