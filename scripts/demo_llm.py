"""Демо Инкремента 1: LLM за единым портом.

Собирает роутер провайдеров (сейчас — локальный Ollama; Anthropic подключится,
когда появится ключ) и делает один вызов, показывая ответ, расход токенов,
стоимость и латентность. Мультипровайдерность и учёт бюджета — в одном месте.

    uv run python scripts/demo_llm.py "Твой промпт"
"""

from __future__ import annotations

import argparse

from app.adapters.llm.ollama import OllamaProvider
from app.adapters.llm.router import LLMRouter
from app.config import get_settings
from app.domain.llm import Message, Role
from app.domain.ports import LLMProvider
from app.observability.budget import BudgetTracker


def main() -> int:
    parser = argparse.ArgumentParser(description="Демо LLM-порта: один вызов через роутер")
    parser.add_argument("prompt", nargs="?", default="Ответь одним словом: работает?")
    parser.add_argument("--max-tokens", type=int, default=64)
    args = parser.parse_args()

    settings = get_settings()
    providers: dict[str, LLMProvider] = {
        "ollama": OllamaProvider(settings.ollama_model, base_url=settings.ollama_base_url),
    }
    budget = BudgetTracker(limit_usd=settings.llm_budget_usd)
    router = LLMRouter(providers, default=settings.default_llm_provider, budget=budget)

    resp = router.generate([Message(Role.USER, args.prompt)], max_tokens=args.max_tokens)

    print(f"провайдер: {resp.provider} · модель: {resp.model}")
    print(
        f"токены: prompt={resp.usage.prompt_tokens} "
        f"completion={resp.usage.completion_tokens} total={resp.usage.total_tokens}"
    )
    print(f"стоимость: ${resp.cost_usd:.4f} · латентность: {resp.latency_ms:.0f} мс")
    print(f"бюджет: потрачено ${budget.spent_usd:.4f}, вызовов {budget.calls}")
    print("─" * 44)
    print(resp.text.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
