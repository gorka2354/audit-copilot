"""Маппинг доменных исключений в HTTP-ответы.

Домен и агент кидают свои типы (`BudgetExceeded`, `LLMError`) и ничего не знают
про HTTP-коды — соответствие живёт здесь, на границе. Так один и тот же агент
работает и в CLI-демо, и под API без изменений.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout

from app.domain.llm import LLMError
from app.observability.budget import BudgetExceeded


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(BudgetExceeded)
    async def _budget(request: Request, exc: BudgetExceeded) -> JSONResponse:
        # бюджет LLM исчерпан — это квота, а не ошибка сервера
        return JSONResponse(
            status_code=429, content={"error": "budget_exceeded", "detail": str(exc)}
        )

    @app.exception_handler(LLMError)
    async def _llm(request: Request, exc: LLMError) -> JSONResponse:
        # терминальная ошибка апстрим-провайдера (напр. 401/400) — сбой шлюза
        return JSONResponse(status_code=502, content={"error": "llm_upstream", "detail": str(exc)})

    @app.exception_handler(PoolTimeout)
    async def _pool(request: Request, exc: PoolTimeout) -> JSONResponse:
        # все коннекшны пула заняты дольше таймаута — временная перегрузка, не 500
        return JSONResponse(
            status_code=503, content={"error": "pool_exhausted", "detail": str(exc)}
        )
