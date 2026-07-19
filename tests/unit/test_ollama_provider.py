"""Юнит-тесты Ollama-провайдера с мок-транспортом httpx (без живого демона)."""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from app.adapters.llm.ollama import OllamaProvider
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
