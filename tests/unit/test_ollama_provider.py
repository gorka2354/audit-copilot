"""Юнит-тесты Ollama-провайдера с мок-транспортом httpx (без живого демона)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.adapters.llm.ollama import OllamaError, OllamaProvider
from app.domain.llm import Message, Role


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_parses_ollama_response_into_domain() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hello"},
                "prompt_eval_count": 11,
                "eval_count": 7,
            },
        )

    provider = OllamaProvider("qwen2.5-coder:7b", client=_client(handler))
    resp = provider.generate([Message(Role.USER, "hi")], temperature=0.2, max_tokens=64)

    assert resp.text == "hello"
    assert resp.provider == "ollama"
    assert resp.model == "qwen2.5-coder:7b"
    assert resp.usage.prompt_tokens == 11
    assert resp.usage.completion_tokens == 7
    assert resp.usage.total_tokens == 18
    assert resp.cost_usd == 0.0
    assert resp.latency_ms >= 0.0

    body = json.loads(sent[0].content)
    assert str(sent[0].url).endswith("/api/chat")
    assert body["model"] == "qwen2.5-coder:7b"
    assert body["stream"] is False
    assert body["options"]["temperature"] == 0.2
    assert body["options"]["num_predict"] == 64
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_missing_usage_defaults_to_zero() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": "x"}})

    provider = OllamaProvider("m", client=_client(handler))
    resp = provider.generate([Message(Role.USER, "hi")])
    assert resp.usage.total_tokens == 0
    assert resp.text == "x"


def test_http_error_preserves_ollama_detail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'x' not found"})

    provider = OllamaProvider("x", client=_client(handler))
    with pytest.raises(OllamaError, match="not found"):
        provider.generate([Message(Role.USER, "hi")])


def test_error_field_in_200_body_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "the model failed to generate a response"})

    provider = OllamaProvider("m", client=_client(handler))
    with pytest.raises(OllamaError, match="failed to generate"):
        provider.generate([Message(Role.USER, "hi")])


def test_missing_message_raises_clear_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"prompt_eval_count": 1})

    provider = OllamaProvider("m", client=_client(handler))
    with pytest.raises(OllamaError):
        provider.generate([Message(Role.USER, "hi")])


def test_no_max_tokens_omits_num_predict() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"message": {"content": "x"}})

    provider = OllamaProvider("m", client=_client(handler))
    provider.generate([Message(Role.USER, "hi")])
    body = json.loads(sent[0].content)
    assert "num_predict" not in body["options"]
