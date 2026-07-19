"""Роутер LLM-провайдеров за единым портом.

Держит несколько провайдеров (Ollama, Anthropic, …), выбирает по имени или по
дефолту, при отказе делает fallback на следующий и ведёт учёт бюджета. Для
вызывающего кода это по-прежнему один `generate()` — конкретный провайдер скрыт.
"""

from __future__ import annotations

import logging

from app.domain.llm import LLMResponse, Message
from app.domain.ports import LLMProvider
from app.observability.budget import BudgetTracker

_log = logging.getLogger(__name__)


class LLMRouter:
    def __init__(
        self,
        providers: dict[str, LLMProvider],
        *,
        default: str,
        budget: BudgetTracker | None = None,
    ):
        if not providers:
            raise ValueError("нужен хотя бы один провайдер")
        if default not in providers:
            raise ValueError(f"default-провайдер '{default}' не среди {list(providers)}")
        self._providers = providers
        self._default = default
        self._budget = budget if budget is not None else BudgetTracker()

    @property
    def budget(self) -> BudgetTracker:
        return self._budget

    def generate(
        self,
        messages: list[Message],
        *,
        provider: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        fallback: bool = True,
    ) -> LLMResponse:
        self._budget.check()
        order = self._resolve_order(provider, fallback)
        last_error: Exception | None = None
        for name in order:
            try:
                response = self._providers[name].generate(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
            except Exception as exc:  # пробуем следующий провайдер в цепочке fallback
                last_error = exc
                _log.warning("LLM-провайдер '%s' отказал: %s", name, exc)
                continue
            if name != order[0]:
                _log.warning("fallback: ответ от '%s' вместо запрошенного '%s'", name, order[0])
            self._budget.record(response)
            return response
        raise RuntimeError(f"все провайдеры отказали: {order}") from last_error

    def _resolve_order(self, provider: str | None, fallback: bool) -> list[str]:
        primary = provider or self._default
        if primary not in self._providers:
            raise ValueError(f"провайдер '{primary}' не зарегистрирован")
        if not fallback:
            return [primary]
        rest = [name for name in self._providers if name != primary]
        return [primary, *rest]
