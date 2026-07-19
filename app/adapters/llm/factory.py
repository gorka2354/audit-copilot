"""Композиционный корень LLM-слоя: сборка роутера из настроек.

Единственное место, где провайдеры регистрируются под ключами, равными их
`provider.name` — это исключает рассинхрон «ключ роутера ≠ имя провайдера».
Anthropic подключается, только если задан ключ; иначе дефолт откатывается на Ollama.
"""

from __future__ import annotations

from app.adapters.llm.anthropic import AnthropicProvider
from app.adapters.llm.ollama import OllamaProvider
from app.adapters.llm.router import LLMRouter
from app.config import Settings
from app.domain.ports import LLMProvider
from app.observability.budget import BudgetTracker

_KNOWN_PROVIDERS = frozenset({AnthropicProvider.name, OllamaProvider.name})


def build_router(settings: Settings) -> LLMRouter:
    providers: dict[str, LLMProvider] = {}

    if settings.anthropic_api_key is not None:
        providers[AnthropicProvider.name] = AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value(),
            model=settings.anthropic_model,
        )

    providers[OllamaProvider.name] = OllamaProvider(
        settings.ollama_model, base_url=settings.ollama_base_url
    )

    default = settings.default_llm_provider
    if default not in _KNOWN_PROVIDERS:
        raise ValueError(
            f"неизвестный default_llm_provider '{default}'; допустимо: {sorted(_KNOWN_PROVIDERS)}"
        )
    # Известный, но недоступный (напр. anthropic без ключа) — осознанный откат на ollama.
    if default not in providers:
        default = OllamaProvider.name

    budget = BudgetTracker(limit_usd=settings.llm_budget_usd)
    return LLMRouter(providers, default=default, budget=budget)
