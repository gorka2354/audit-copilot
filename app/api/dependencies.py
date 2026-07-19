"""FastAPI-зависимости: отдают адаптеры, поднятые в lifespan и лежащие в `app.state`.

Один инстанс на процесс (создан в lifespan), а не на запрос — соединения и
клиенты не пересоздаются. Порты возвращаются как доменные типы, поэтому роуты
зависят от абстракций, а не от конкретных адаптеров.
"""

from __future__ import annotations

from typing import cast

from fastapi import Request

from app.adapters.llm.router import LLMRouter
from app.config import Settings
from app.domain.ports import Embedder, StaticAnalyzer, VectorStore


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_analyzer(request: Request) -> StaticAnalyzer:
    return cast(StaticAnalyzer, request.app.state.analyzer)


def get_embedder(request: Request) -> Embedder:
    return cast(Embedder, request.app.state.embedder)


def get_store(request: Request) -> VectorStore:
    return cast(VectorStore, request.app.state.store)


def get_router(request: Request) -> LLMRouter:
    return cast(LLMRouter, request.app.state.router)
