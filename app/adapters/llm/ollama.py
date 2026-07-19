"""Адаптер локального Ollama за портом `LLMProvider`.

Чистый HTTP к демону Ollama (`POST /api/chat`), без внешних SDK. Локальный
инференс — стоимость всегда 0; расход токенов берём из ответа
(`prompt_eval_count` / `eval_count`).
"""

from __future__ import annotations

import time
from types import TracebackType

import httpx

from app.domain.llm import LLMResponse, Message, TokenUsage

# connect держим коротким, read — большим: генерация 7b на CPU и холодный старт
# модели (load_duration) бывают долгими, а вот на установку соединения столько ждать незачем.
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=180.0, write=10.0, pool=5.0)


class OllamaError(RuntimeError):
    """Ошибка вызова Ollama — с сохранённым текстом от демона."""


class OllamaProvider:
    """`LLMProvider` поверх локального демона Ollama."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "http://localhost:11434",
        client: httpx.Client | None = None,
        timeout: httpx.Timeout | float | None = None,
    ):
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout or _DEFAULT_TIMEOUT)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaProvider:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

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
        latency_ms = (time.perf_counter() - started) * 1000.0

        if response.status_code >= 400:
            raise OllamaError(f"Ollama HTTP {response.status_code}: {self._error_detail(response)}")

        data = response.json()
        # Ollama при ошибке генерации может ответить 200 с телом {"error": ...} (без message).
        if isinstance(data, dict) and data.get("error"):
            raise OllamaError(str(data["error"]))
        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, dict) or "content" not in message:
            raise OllamaError(f"Ollama вернул ответ без message.content: {data!r}")

        usage = TokenUsage(
            prompt_tokens=int(data.get("prompt_eval_count", 0)),
            completion_tokens=int(data.get("eval_count", 0)),
        )
        return LLMResponse(
            text=message["content"],
            model=self.model,
            provider=self.name,
            usage=usage,
            cost_usd=0.0,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        """Достать текст ошибки Ollama из тела ответа (поле `error`), не потеряв его."""
        try:
            body = response.json()
        except ValueError:
            return response.text[:200]
        if isinstance(body, dict) and "error" in body:
            return str(body["error"])
        return response.text[:200]
