"""Адаптер эмбеддингов Ollama (nomic-embed-text) за портом `Embedder`.

Тот же демон Ollama, что и для генерации (`POST /api/embed`) — на мини-ПК.
Батч-векторизация; размерность модели фиксирована (nomic-embed-text → 768).
"""

from __future__ import annotations

from typing import cast

import httpx

_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=5.0)


class EmbedderError(RuntimeError):
    """Ошибка векторизации."""


class OllamaEmbedder:
    """`Embedder` поверх Ollama `/api/embed`."""

    name = "ollama"

    def __init__(
        self,
        model: str = "nomic-embed-text",
        *,
        base_url: str = "http://localhost:11434",
        dimension: int = 768,
        client: httpx.Client | None = None,
    ):
        self.model = model
        self.dimension = dimension
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=_DEFAULT_TIMEOUT)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.post(
                f"{self._base_url}/api/embed", json={"model": self.model, "input": texts}
            )
        except httpx.HTTPError as exc:
            raise EmbedderError(f"Ollama embed transport error: {exc}") from exc

        if response.status_code >= 400:
            raise EmbedderError(f"Ollama embed HTTP {response.status_code}: {response.text[:200]}")

        data = response.json()
        embeddings = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise EmbedderError(
                f"Ollama embed: ждали {len(texts)} векторов, получили {data!r}"[:300]
            )
        if any(len(vec) != self.dimension for vec in embeddings):
            got = len(embeddings[0]) if embeddings else "?"
            raise EmbedderError(
                f"Ollama embed: размерность ≠ {self.dimension} "
                f"(модель {self.model} вернула {got}) — проверь embed_dimension/схему"
            )
        return cast(list[list[float]], embeddings)

    def close(self) -> None:
        self._client.close()
