"""Композиционный корень HTTP-слоя: `create_app` + lifespan.

lifespan поднимает тяжёлые адаптеры (пул Postgres, эмбеддер, LLM-роутер,
анализатор) один раз на процесс и кладёт их в `app.state`; зависимости в
`dependencies.py` раздают их по запросам. На shutdown закрывается пул соединений.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.adapters.analyzer.security_lab import SecurityLabAnalyzer
from app.adapters.embedder.ollama_embed import OllamaEmbedder
from app.adapters.llm.factory import build_router
from app.adapters.vectorstore.pgvector_store import PgVectorStore
from app.api.routes import router as api_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    store = PgVectorStore.from_dsn_pool(settings.database_url, dimension=settings.embed_dimension)
    app.state.settings = settings
    app.state.analyzer = SecurityLabAnalyzer.from_path(settings.recon_toolkit_path)
    app.state.embedder = OllamaEmbedder(
        settings.embed_model, base_url=settings.ollama_base_url, dimension=settings.embed_dimension
    )
    app.state.store = store
    app.state.router = build_router(settings)
    try:
        yield
    finally:
        store.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="audit-copilot",
        version="0.1.0",
        summary="AI-аудитор смарт-контрактов: статические детекторы + RAG + агент",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    return app
