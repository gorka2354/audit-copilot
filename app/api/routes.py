"""HTTP-роуты. Тонкие: разбирают запрос, зовут агент/RAG за портами, отдают DTO."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.adapters.llm.router import LLMRouter
from app.api.dependencies import get_router
from app.api.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health(llm: Annotated[LLMRouter, Depends(get_router)]) -> HealthResponse:
    """Живость процесса и конфигурация LLM — без сетевых вызовов к провайдерам."""
    return HealthResponse(
        status="ok",
        llm_provider=llm.default,
        model=llm.model,
        providers=llm.provider_names,
    )
