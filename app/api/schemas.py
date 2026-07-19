"""Pydantic-DTO HTTP-слоя.

Граница между доменом и HTTP: домен — frozen dataclass'ы без зависимостей, эти
DTO — их сериализуемое представление. Конвертация домен→DTO живёт здесь
(`from_domain`), домен про pydantic и HTTP не знает.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.audit import AuditFinding, AuditReport, Citation
from app.domain.rag import RetrievedChunk


class HealthResponse(BaseModel):
    """Живость процесса и конфигурация LLM (без сетевых проверок)."""

    status: str
    llm_provider: str
    model: str
    providers: list[str]


class AuditRequest(BaseModel):
    """Тело `POST /audit` — исходник контракта и параметры прогона."""

    code: str = Field(min_length=1, description="Исходный код Solidity-контракта")
    path: str = Field(default="contract.sol", description="Имя файла для отчёта")
    top_k: int = Field(default=4, ge=1, le=20, description="Фрагментов контекста на находку")
    rerank: bool = Field(default=False, description="Включить LLM-реранк RAG-контекста")


class CitationDTO(BaseModel):
    source: str
    snippet: str

    @classmethod
    def from_domain(cls, citation: Citation) -> CitationDTO:
        return cls(source=citation.source, snippet=citation.snippet)


class FindingDTO(BaseModel):
    detector: str
    title: str
    file: str
    line: int
    severity: str
    rationale: str
    fix: str
    citations: list[CitationDTO]

    @classmethod
    def from_domain(cls, finding: AuditFinding) -> FindingDTO:
        return cls(
            detector=finding.detector,
            title=finding.title,
            file=finding.location.file,
            line=finding.location.line,
            severity=finding.severity.value,
            rationale=finding.rationale,
            fix=finding.fix,
            citations=[CitationDTO.from_domain(c) for c in finding.citations],
        )


class AuditReportDTO(BaseModel):
    contract: str
    high_count: int
    findings: list[FindingDTO]

    @classmethod
    def from_domain(cls, report: AuditReport) -> AuditReportDTO:
        return cls(
            contract=report.contract,
            high_count=report.high_count,
            findings=[FindingDTO.from_domain(f) for f in report.findings],
        )


class SearchRequest(BaseModel):
    """Тело `POST /search` — запрос к базе знаний по безопасности."""

    query: str = Field(min_length=1, description="Поисковый запрос")
    top_k: int = Field(default=5, ge=1, le=50)
    vuln_class: str | None = Field(default=None, description="Сузить до класса уязвимости")
    rerank: bool = Field(default=False, description="Включить LLM-реранк")


class SearchResultDTO(BaseModel):
    chunk_id: str
    source: str
    score: float
    content: str

    @classmethod
    def from_domain(cls, hit: RetrievedChunk) -> SearchResultDTO:
        return cls(
            chunk_id=hit.chunk.id,
            source=hit.chunk.source,
            score=hit.score,
            content=hit.chunk.content,
        )


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultDTO]
