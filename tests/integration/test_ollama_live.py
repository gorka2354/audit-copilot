"""Интеграция с живым Ollama. Пропускается, если демон или модель недоступны."""

from __future__ import annotations

import httpx
import pytest

from app.adapters.llm.ollama import OllamaProvider
from app.config import get_settings
from app.domain.llm import Message, Role


@pytest.mark.integration
def test_ollama_generates() -> None:
    settings = get_settings()
    base = settings.ollama_base_url
    try:
        tags = httpx.get(f"{base}/api/tags", timeout=2.0)
        tags.raise_for_status()
    except Exception:
        pytest.skip("Ollama-демон недоступен")

    available = [m["name"] for m in tags.json().get("models", [])]
    family = settings.ollama_model.split(":")[0]
    if not any(family in name for name in available):
        pytest.skip(f"модель {settings.ollama_model} не загружена (есть: {available})")

    provider = OllamaProvider(
        settings.ollama_model,
        base_url=base,
        # 7b на CPU/холодном старте грузится долго — даём read с большим запасом.
        timeout=httpx.Timeout(connect=5.0, read=600.0, write=10.0, pool=5.0),
    )
    resp = provider.generate(
        [Message(Role.USER, "Reply with the single word: ok")],
        max_tokens=10,
    )
    assert resp.text.strip()
    assert resp.usage.completion_tokens > 0
    assert resp.provider == "ollama"
