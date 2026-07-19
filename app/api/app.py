"""Композиционный корень HTTP-слоя: `create_app` + lifespan.

lifespan поднимает тяжёлые адаптеры (пул Postgres, эмбеддер, LLM-роутер,
анализатор) один раз на процесс и кладёт их в `app.state`; зависимости в
`dependencies.py` раздают их по запросам. На shutdown закрывается пул соединений.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI

from app.adapters.analyzer.security_lab import SecurityLabAnalyzer
from app.adapters.embedder.ollama_embed import OllamaEmbedder
from app.adapters.llm.factory import build_router
from app.adapters.vectorstore.factory import build_store
from app.api.errors import register_error_handlers
from app.api.routes import router as api_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # ExitStack регистрирует close по мере создания: если инициализация упадёт на
    # середине (напр. неверный SECURITY_LAB_PATH), уже открытые ресурсы (в первую
    # очередь пул Postgres) закроются, а не утекут. На shutdown — то же самое.
    with ExitStack() as stack:
        store = build_store(settings)
        stack.callback(store.close)
        embedder = OllamaEmbedder(
            settings.embed_model,
            base_url=settings.ollama_base_url,
            dimension=settings.embed_dimension,
        )
        stack.callback(embedder.close)
        router = build_router(settings)
        stack.callback(router.close)

        app.state.settings = settings
        app.state.analyzer = SecurityLabAnalyzer.from_path(settings.recon_toolkit_path)
        app.state.embedder = embedder
        app.state.store = store
        app.state.router = router
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="audit-copilot",
        version="0.1.0",
        summary="AI-аудитор смарт-контрактов: статические детекторы + RAG + агент",
        lifespan=lifespan,
    )
    app.include_router(api_router)
    register_error_handlers(app)
    return app
