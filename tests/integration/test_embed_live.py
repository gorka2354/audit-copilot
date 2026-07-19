"""Интеграция: живой эмбеддинг через Ollama (мини-ПК). Skip, если недоступен."""

from __future__ import annotations

import httpx
import pytest

from app.adapters.embedder.ollama_embed import OllamaEmbedder
from app.config import get_settings


@pytest.mark.integration
def test_ollama_embed_live() -> None:
    settings = get_settings()
    base = settings.ollama_base_url
    try:
        httpx.get(f"{base}/api/tags", timeout=3.0).raise_for_status()
    except Exception:
        pytest.skip("Ollama недоступен")

    emb = OllamaEmbedder(
        settings.embed_model, base_url=base, dimension=settings.embed_dimension
    )
    vecs = emb.embed(["reentrancy vulnerability", "missing access control"])
    assert len(vecs) == 2
    assert all(len(v) == settings.embed_dimension for v in vecs)
