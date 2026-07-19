"""FastAPI-зависимости: отдают адаптеры, поднятые в lifespan и лежащие в `app.state`.

Один инстанс на процесс (создан в lifespan), а не на запрос — соединения и
клиенты не пересоздаются. Порты возвращаются как доменные типы, поэтому роуты
зависят от абстракций, а не от конкретных адаптеров.
"""

from __future__ import annotations

import hmac
from typing import cast

from fastapi import Header, HTTPException, Request

from app.adapters.llm.router import LLMRouter
from app.config import Settings
from app.config import get_settings as _load_settings
from app.domain.ports import Embedder, StaticAnalyzer, VectorStore


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Если в настройках задан `api_key` — требовать совпадающий заголовок X-API-Key.

    `api_key=None` (по умолчанию) — эндпоинт открыт (локальное демо). Иначе отсутствие
    или несовпадение заголовка → 401. Защита от чужих трат LLM на публичном деплое.
    """
    api_key = _load_settings().api_key
    if api_key is None:
        return
    # constant-time сравнение: обычный `!=` протекает длину совпавшего префикса
    # по времени и даёт side-channel на побайтовый подбор ключа
    if x_api_key is None or not hmac.compare_digest(x_api_key, api_key.get_secret_value()):
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key")


def get_analyzer(request: Request) -> StaticAnalyzer:
    return cast(StaticAnalyzer, request.app.state.analyzer)


def get_embedder(request: Request) -> Embedder:
    return cast(Embedder, request.app.state.embedder)


def get_store(request: Request) -> VectorStore:
    return cast(VectorStore, request.app.state.store)


def get_router(request: Request) -> LLMRouter:
    return cast(LLMRouter, request.app.state.router)
