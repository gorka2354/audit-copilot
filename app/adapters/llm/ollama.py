"""Адаптер локального Ollama за портом `LLMProvider`.

Чистый HTTP к демону Ollama (`POST /api/chat`), без внешних SDK. Локальный
инференс — стоимость всегда 0; расход токенов берём из ответа
(`prompt_eval_count` / `eval_count`).
"""

from __future__ import annotations

import time

import httpx

from app.domain.llm import LLMResponse, Message, TokenUsage


class OllamaProvider:
    """`LLMProvider` поверх локального демона Ollama."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "http://localhost:11434",
        client: httpx.Client | None = None,
        timeout: float = 120.0,
    ):
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        options: dict[str, float | int] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "stream": False,
            "options": options,
        }

        started = time.perf_counter()
        response = self._client.post(f"{self._base_url}/api/chat", json=payload)
        response.raise_for_status()
        latency_ms = (time.perf_counter() - started) * 1000.0

        data = response.json()
        usage = TokenUsage(
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
        )
        return LLMResponse(
            text=data["message"]["content"],
            model=self.model,
            provider=self.name,
            usage=usage,
            cost_usd=0.0,
            latency_ms=latency_ms,
        )
