"""Демо Инкремента 3 (кульминация): агент-аудитор смарт-контракта.

Полная вертикаль: recon находит сигналы → агент маршрутизирует каждый в свой
класс базы знаний → RAG достаёт контекст → LLM обогащает (severity, обоснование,
фикс, цитаты с провенансом) → человекочитаемый отчёт со стоимостью прогона.

    # первый запуск: заодно проиндексировать корпус
    uv run python scripts/demo_audit.py --ingest
    # обычный запуск на своём контракте, с LLM-реранком и трейсом цепочки
    uv run python scripts/demo_audit.py path/to/Contract.sol --rerank --trace
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from app.adapters.analyzer.security_lab import SecurityLabAnalyzer
from app.adapters.embedder.ollama_embed import OllamaEmbedder
from app.adapters.llm.factory import build_router
from app.adapters.vectorstore.factory import build_store
from app.agent.auditor import audit_contract
from app.config import get_settings
from app.domain.audit import AuditReport
from app.domain.models import Severity, SoliditySource
from app.observability.budget import BudgetTracker
from app.rag.ingest import collect_corpus, ingest

_MARKER = {Severity.HIGH: "[!]", Severity.MEDIUM: "[.]", Severity.LOW: "[ ]", Severity.INFO: "[i]"}
_ORDER = [Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]


def _render(report: AuditReport, provider: str) -> str:
    counts = {s: sum(1 for f in report.findings if f.severity is s) for s in _ORDER}
    badges = "  ".join(f"{_MARKER[s]}{counts[s]}" for s in _ORDER if counts[s])
    header = (
        f"{report.contract} — аудит: {len(report.findings)} находок  {badges}  (LLM: {provider})"
    )
    lines = [header, "═" * len(header)]

    ordered = sorted(report.findings, key=lambda f: _ORDER.index(f.severity))
    for f in ordered:
        lines.append(f"\n{_MARKER[f.severity]} {f.location}  {f.title}  (detector: {f.detector})")
        if f.rationale:
            lines.append(f"    обоснование: {f.rationale}")
        if f.fix:
            lines.append(f"    фикс: {f.fix}")
        if f.citations:
            lines.append("    источники:")
            for c in f.citations:
                snippet = " ".join(c.snippet.split())[:180]
                lines.append(f"      - {c.source}")
                lines.append(f"        «{snippet}…»")
    return "\n".join(lines)


def _render_budget(budget: BudgetTracker) -> str:
    return (
        f"\n── бюджет прогона: {budget.calls} вызовов LLM, "
        f"{budget.usage.total_tokens} токенов, ${budget.spent_usd:.4f} ──"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Демо агента-аудитора смарт-контрактов")
    parser.add_argument(
        "sol_file", type=Path, nargs="?", default=Path("examples/VulnerableVault.sol")
    )
    parser.add_argument(
        "--ingest", action="store_true", help="переиндексировать корпус перед аудитом"
    )
    parser.add_argument("--rerank", action="store_true", help="включить LLM-реранк RAG-контекста")
    parser.add_argument("--top-k", type=int, default=4, help="фрагментов контекста на находку")
    parser.add_argument("--trace", action="store_true", help="показать трейс цепочки (INFO-логи)")
    args = parser.parse_args()

    if args.trace:
        logging.basicConfig(level=logging.INFO, format="  · %(message)s")

    settings = get_settings()
    analyzer = SecurityLabAnalyzer.from_path(settings.recon_toolkit_path)
    embedder = OllamaEmbedder(
        settings.embed_model, base_url=settings.ollama_base_url, dimension=settings.embed_dimension
    )
    store = build_store(settings)
    router = build_router(settings)

    try:
        if args.ingest:
            docs = collect_corpus(settings.security_lab_path)
            count = ingest(docs, embedder, store)
            print(f"проиндексировано: {count} чанков из {len(docs)} документов\n")

        code = args.sol_file.read_text(encoding="utf-8", errors="ignore")
        source = SoliditySource(path=args.sol_file.name, code=code)
        report = audit_contract(
            source,
            analyzer,
            embedder,
            store,
            router,
            reranker=router if args.rerank else None,
            top_k=args.top_k,
        )

        print(_render(report, router.default))
        print(_render_budget(router.budget))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
