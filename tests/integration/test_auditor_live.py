"""Интеграция: аудитор против живого стека (recon + Ollama + pgvector + LLM).

Самодостаточен: ингестит контролируемый мини-корпус в собственный source, гоняет
цепочку на уязвимом контракте и проверяет end-to-end инварианты. Ассерты устойчивы
к недетерминизму LLM — проверяем провенанс и структуру, а не конкретные severity.
Skip, если инфраструктура недоступна (Postgres/Ollama).
"""

from __future__ import annotations

import psycopg
import pytest

from app.adapters.analyzer.security_lab import SecurityLabAnalyzer
from app.adapters.embedder.ollama_embed import OllamaEmbedder
from app.adapters.llm.factory import build_router
from app.adapters.vectorstore.pgvector_store import PgVectorStore
from app.agent.auditor import audit_contract
from app.config import get_settings
from app.domain.models import Severity, SoliditySource
from app.domain.rag import Chunk

_LIVE_SOURCE = "audit-live-corpus"

_MINI_CORPUS = [
    Chunk(
        id=f"{_LIVE_SOURCE}#reentrancy",
        source=_LIVE_SOURCE,
        content="Reentrancy: an external call before the state write violates "
        "checks-effects-interactions; add nonReentrant and update balances before the call.",
        metadata={"class": "reentrancy"},
    ),
    Chunk(
        id=f"{_LIVE_SOURCE}#access",
        source=_LIVE_SOURCE,
        content="Access control: a privileged setter without onlyOwner lets any caller seize "
        "ownership; gate it with an authorization modifier.",
        metadata={"class": "access"},
    ),
]

_CONTRACT = """// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
contract Reentrant {
    mapping(address => uint256) public bal;
    address public owner;
    function withdraw(uint256 a) external {
        require(bal[msg.sender] >= a);
        (bool ok, ) = msg.sender.call{value: a}("");
        require(ok);
        bal[msg.sender] -= a;
    }
    function setOwner(address o) external { owner = o; }
}
"""


@pytest.mark.integration
def test_audit_contract_end_to_end() -> None:
    settings = get_settings()
    try:
        conn = psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    embedder = OllamaEmbedder(
        settings.embed_model, base_url=settings.ollama_base_url, dimension=settings.embed_dimension
    )
    try:
        embeddings = embedder.embed([c.content for c in _MINI_CORPUS])
    except Exception:  # Ollama-мини-ПК недоступен
        conn.close()
        pytest.skip("Ollama недоступен — эмбеддер не отвечает")

    analyzer = SecurityLabAnalyzer.from_path(settings.recon_toolkit_path)
    store = PgVectorStore(settings.database_url, dimension=settings.embed_dimension, conn=conn)
    router = build_router(settings)

    try:
        store.replace_source(_LIVE_SOURCE, _MINI_CORPUS, embeddings)
        source = SoliditySource(path="Reentrant.sol", code=_CONTRACT)

        raw = analyzer.analyze(source)
        assert raw, "recon должен найти хотя бы одну находку в заведомо уязвимом контракте"

        report = audit_contract(source, analyzer, embedder, store, router)

        # обогащение 1:1 — агент ничего не теряет и не выдумывает поверх recon
        assert report.contract == "Reentrant.sol"
        assert len(report.findings) == len(raw)
        for finding in report.findings:
            assert finding.detector  # провенанс детектора
            assert finding.severity in set(Severity)
            assert finding.rationale  # всегда заполнено (LLM или fallback-note)
            # провенанс цитат: каждая воспроизводима из реального источника
            for citation in finding.citations:
                assert citation.source
                assert citation.snippet
    finally:
        conn.execute("DELETE FROM chunks WHERE source = %s", (_LIVE_SOURCE,))
        store.close()
