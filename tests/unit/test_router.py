"""Юнит-тесты LLMRouter с фейковыми провайдерами."""

from __future__ import annotations

import pytest

from app.adapters.llm.router import LLMRouter
from app.domain.llm import LLMResponse, Message, Role, TokenUsage


class _FakeProvider:
    def __init__(self, name: str, *, fail: bool = False, cost: float = 0.0):
        self.name = name
        self.model = f"{name}-model"
        self._fail = fail
        self._cost = cost
        self.calls = 0

    def generate(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        self.calls += 1
        if self._fail:
            raise RuntimeError(f"{self.name} down")
        return LLMResponse(
            text=f"from {self.name}",
            model=self.model,
            provider=self.name,
            usage=TokenUsage(3, 4),
            cost_usd=self._cost,
            latency_ms=1.0,
        )


_MSG = [Message(Role.USER, "hi")]


def test_routes_to_default() -> None:
    router = LLMRouter({"a": _FakeProvider("a"), "b": _FakeProvider("b")}, default="a")
    resp = router.generate(_MSG)
    assert resp.provider == "a"
    assert router.budget.calls == 1


def test_explicit_provider_selection() -> None:
    router = LLMRouter({"a": _FakeProvider("a"), "b": _FakeProvider("b")}, default="a")
    resp = router.generate(_MSG, provider="b")
    assert resp.provider == "b"


def test_fallback_on_failure() -> None:
    a, b = _FakeProvider("a", fail=True), _FakeProvider("b")
    router = LLMRouter({"a": a, "b": b}, default="a")
    resp = router.generate(_MSG)
    assert resp.provider == "b"  # a упал → fallback на b
    assert a.calls == 1
    assert b.calls == 1


def test_no_fallback_raises() -> None:
    a, b = _FakeProvider("a", fail=True), _FakeProvider("b")
    router = LLMRouter({"a": a, "b": b}, default="a")
    with pytest.raises(RuntimeError):
        router.generate(_MSG, fallback=False)
    assert b.calls == 0  # b не трогали


def test_budget_records_cost() -> None:
    router = LLMRouter({"a": _FakeProvider("a", cost=0.01)}, default="a")
    router.generate(_MSG)
    router.generate(_MSG)
    assert abs(router.budget.spent_usd - 0.02) < 1e-9


def test_unknown_default_rejected() -> None:
    with pytest.raises(ValueError):
        LLMRouter({"a": _FakeProvider("a")}, default="z")
