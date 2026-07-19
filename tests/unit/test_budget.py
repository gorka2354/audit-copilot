"""Юнит-тесты BudgetTracker."""

from __future__ import annotations

import pytest

from app.domain.llm import LLMResponse, TokenUsage
from app.observability.budget import BudgetExceeded, BudgetTracker


def _resp(cost: float, pt: int = 5, ct: int = 5) -> LLMResponse:
    return LLMResponse(
        text="x",
        model="m",
        provider="p",
        usage=TokenUsage(pt, ct),
        cost_usd=cost,
        latency_ms=1.0,
    )


def test_accumulates_cost_usage_calls() -> None:
    b = BudgetTracker()
    b.record(_resp(0.01))
    b.record(_resp(0.02))
    assert b.calls == 2
    assert abs(b.spent_usd - 0.03) < 1e-9
    assert b.usage.total_tokens == 20


def test_no_limit_means_unlimited() -> None:
    b = BudgetTracker()
    assert b.remaining_usd() is None
    b.check(projected_usd=10_000)  # без лимита не бросает


def test_check_raises_when_over_limit() -> None:
    b = BudgetTracker(limit_usd=0.05)
    b.record(_resp(0.04))
    b.check(projected_usd=0.005)  # 0.045 <= 0.05 — ок
    with pytest.raises(BudgetExceeded):
        b.check(projected_usd=0.02)  # 0.06 > 0.05


def test_remaining_never_negative() -> None:
    b = BudgetTracker(limit_usd=0.05)
    b.record(_resp(0.08))
    assert b.remaining_usd() == 0.0
