"""Демо Инкремента 1: LLM за единым портом.

Собирает роутер провайдеров из настроек (Anthropic, если задан ключ, + локальный
Ollama) и делает один вызов, показывая ответ, расход токенов, стоимость и
латентность. Мультипровайдерность и учёт бюджета — в одном месте.

    uv run python scripts/demo_llm.py "Твой промпт" [--provider ollama]
"""

from __future__ import annotations

import argparse

from app.adapters.llm.factory import build_router
from app.config import get_settings
from app.domain.llm import Message, Role


def main() -> int:
    parser = argparse.ArgumentParser(description="Демо LLM-порта: один вызов через роутер")
    parser.add_argument("prompt", nargs="?", default="Ответь одним словом: работает?")
    parser.add_argument(
        "--provider", default=None, help="ollama | anthropic (по умолчанию — из настроек)"
    )
    parser.add_argument("--max-tokens", type=int, default=64)
    args = parser.parse_args()

    router = build_router(get_settings())
    resp = router.generate(
        [Message(Role.USER, args.prompt)],
        provider=args.provider,
        max_tokens=args.max_tokens,
        fallback=False,
    )

    print(f"провайдер: {resp.provider} · модель: {resp.model}")
    print(
        f"токены: prompt={resp.usage.prompt_tokens} "
        f"completion={resp.usage.completion_tokens} total={resp.usage.total_tokens}"
    )
    print(f"стоимость: ${resp.cost_usd:.4f} · латентность: {resp.latency_ms:.0f} мс")
    print(f"бюджет: потрачено ${router.budget.spent_usd:.4f}, вызовов {router.budget.calls}")
    print("─" * 44)
    print(resp.text.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
