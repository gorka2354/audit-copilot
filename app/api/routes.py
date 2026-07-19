"""HTTP-роуты. Тонкие: разбирают запрос, зовут агент/RAG за портами, отдают DTO."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.adapters.llm.router import LLMRouter
from app.agent.auditor import audit_contract
from app.api.dependencies import (
    get_analyzer,
    get_classifier,
    get_embedder,
    get_router,
    get_store,
    require_api_key,
)
from app.api.schemas import (
    AuditReportDTO,
    AuditRequest,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResultDTO,
)
from app.domain.models import SoliditySource
from app.domain.ports import Classifier, Embedder, StaticAnalyzer, VectorStore
from app.rag.retrieve import retrieve_for_class

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


@router.post(
    "/audit",
    response_model=AuditReportDTO,
    tags=["audit"],
    dependencies=[Depends(require_api_key)],
)
def audit(
    req: AuditRequest,
    analyzer: Annotated[StaticAnalyzer, Depends(get_analyzer)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
    store: Annotated[VectorStore, Depends(get_store)],
    llm: Annotated[LLMRouter, Depends(get_router)],
    classifier: Annotated[Classifier, Depends(get_classifier)],
) -> AuditReportDTO:
    """Аудит одного контракта: recon → RAG(class) → LLM-обогащение находок."""
    source = SoliditySource(path=req.path, code=req.code)
    report = audit_contract(
        source,
        analyzer,
        embedder,
        store,
        llm,
        classifier,
        reranker=llm if req.rerank else None,
        top_k=req.top_k,
    )
    return AuditReportDTO.from_domain(report)


@router.post(
    "/search",
    response_model=SearchResponse,
    tags=["search"],
    dependencies=[Depends(require_api_key)],
)
def search(
    req: SearchRequest,
    embedder: Annotated[Embedder, Depends(get_embedder)],
    store: Annotated[VectorStore, Depends(get_store)],
    llm: Annotated[LLMRouter, Depends(get_router)],
) -> SearchResponse:
    """Гибридный поиск по базе знаний с опциональным class-фильтром и LLM-реранком."""
    hits = retrieve_for_class(
        req.query,
        embedder,
        store,
        vuln_class=req.vuln_class,
        top_k=req.top_k,
        reranker=llm if req.rerank else None,
    )
    return SearchResponse(
        query=req.query,
        results=[SearchResultDTO.from_domain(h) for h in hits],
    )
