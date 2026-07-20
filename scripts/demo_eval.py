"""Демо Инкремента 5: eval-харнесс — измеримое качество аудитора.

Detector-level идёт по всему корпусу офлайн и бесплатно. Agent-level (дорого, LLM)
запускается на подвыборке; cross-model judge включается флагом и работает только
если есть второй провайдер (иначе grounding честно пропускается — не self-judge).

    uv run python scripts/demo_eval.py                       # только детекторы, весь корпус
    uv run python scripts/demo_eval.py --sample 5 --judge    # + агент на 5 контрактах + judge
    uv run python scripts/demo_eval.py --sample 5 --out eval-report   # + отчёты .md/.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.adapters.analyzer.replay import ReplayAnalyzer
from app.adapters.embedder.ollama_embed import OllamaEmbedder
from app.adapters.llm.anthropic import AnthropicProvider
from app.adapters.llm.factory import build_router
from app.adapters.llm.ollama import OllamaProvider
from app.adapters.llm.router import LLMRouter
from app.adapters.vectorstore.factory import build_store
from app.config import Settings, get_settings
from app.domain.ports import LLMProvider
from app.eval.corpus import DeFiVulnLabsCorpus
from app.eval.harness import run_agent_eval, run_detector_eval
from app.eval.report import render_json, render_markdown
from app.rag.classify import build_classifier
from app.rag.ingest import collect_corpus


def _pick_cross_model_judge(
    router: LLMRouter, settings: Settings
) -> tuple[LLMProvider | None, str | None]:
    """Судья — модель, ОТЛИЧНАЯ от генератора. Нет второго провайдера → не судим."""
    if router.default == "anthropic":
        judge: LLMProvider = OllamaProvider(
            settings.ollama_model, base_url=settings.ollama_base_url
        )
        return judge, f"ollama:{settings.ollama_model}"
    if router.default != "anthropic" and settings.anthropic_api_key is not None:
        judge = AnthropicProvider(
            api_key=settings.anthropic_api_key.get_secret_value(), model=settings.anthropic_model
        )
        return judge, f"anthropic:{settings.anthropic_model}"
    print("⚠ cross-model судья недоступен (нужен второй провайдер) — grounding пропущен")
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Eval-харнесс аудитора смарт-контрактов")
    parser.add_argument(
        "--sample", type=int, default=0, help="контрактов на agent-level (0 = детекторы)"
    )
    parser.add_argument(
        "--judge", action="store_true", help="cross-model LLM-judge grounding цитат"
    )
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--out", type=Path, default=None, help="базовое имя для .md/.json отчётов")
    args = parser.parse_args()

    settings = get_settings()
    analyzer = ReplayAnalyzer()  # вхолодную: записанный вывод реального движка
    corpus = DeFiVulnLabsCorpus.vendored()

    detector = run_detector_eval(corpus, analyzer)

    agent = None
    if args.sample > 0:
        embedder = OllamaEmbedder(
            settings.embed_model,
            base_url=settings.ollama_base_url,
            dimension=settings.embed_dimension,
        )
        store = build_store(settings)
        router = build_router(settings)
        known_sources = {rel for rel, _ in collect_corpus(settings.security_lab_path)}
        judge, judge_label = (
            _pick_cross_model_judge(router, settings) if args.judge else (None, None)
        )
        covered = [c for c in corpus.cases() if c.is_covered][: args.sample]
        try:
            agent = run_agent_eval(
                covered,
                analyzer,
                embedder,
                store,
                router,
                build_classifier(settings, embedder),
                known_sources,
                top_k=args.top_k,
                judge=judge,
                judge_label=judge_label,
            )
        finally:
            store.close()

    markdown = render_markdown(detector, agent)
    print(markdown)
    if args.out is not None:
        args.out.with_suffix(".md").write_text(markdown, encoding="utf-8")
        args.out.with_suffix(".json").write_text(render_json(detector, agent), encoding="utf-8")
        print(f"\nотчёты сохранены: {args.out}.md / {args.out}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
