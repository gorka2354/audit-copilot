"""Учёт расхода токенов и стоимости LLM-вызовов.

Аккумулятор с опциональным лимитом: показывает суммарную стоимость прогона и
позволяет остановиться, когда бюджет исчерпан. Контроль бюджета — сквозная
забота, поэтому живёт в observability, а не в конкретном провайдере.

Потокобезопасность (soft-cap): `record`/`check`/`remaining_usd` атомарны каждый по
отдельности (Lock), поэтому под конкурентным API нет потерянных обновлений `+=`.
Но `check` и `record` разнесены сетевым LLM-вызовом, а держать Lock через сеть
нельзя (это сериализовало бы все вызовы). Значит N параллельных вызовов могут
пройти `check` до того, как первый сделает `record`, и превысить лимит на стоимость
параллельного окна. Это осознанный soft-cap: точный hard-cap (reserve-паттерн) —
вне скоупа, тем более что путь по умолчанию выключен (`llm_budget_usd=None`).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from app.domain.llm import LLMResponse, TokenUsage


class BudgetExceeded(RuntimeError):
    """Очередной вызов превысил бы лимит стоимости."""


@dataclass
class BudgetTracker:
    limit_usd: float | None = None
    spent_usd: float = 0.0
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(0, 0))
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record(self, response: LLMResponse) -> None:
        """Учесть завершённый вызов (атомарно — без потерянных `+=` под конкуренцией)."""
        with self._lock:
            self.spent_usd += response.cost_usd
            self.usage += response.usage
            self.calls += 1

    def remaining_usd(self) -> float | None:
        """Остаток бюджета, либо None если лимит не задан."""
        if self.limit_usd is None:
            return None
        with self._lock:
            return max(0.0, self.limit_usd - self.spent_usd)

    def check(self, projected_usd: float = 0.0) -> None:
        """Убедиться, что бюджет ещё есть (с учётом ожидаемой стоимости вызова)."""
        with self._lock:
            if self.limit_usd is not None and self.spent_usd + projected_usd > self.limit_usd:
                raise BudgetExceeded(
                    f"Бюджет исчерпан: потрачено ${self.spent_usd:.4f}, лимит ${self.limit_usd:.4f}"
                )
