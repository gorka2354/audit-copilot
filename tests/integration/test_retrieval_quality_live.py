"""Интеграция: качество retrieval на независимом gold-set (nDCG/MRR/recall@k).

Ingest vendored-корпуса → для каждого gold-запроса `hybrid_retrieve` → ранжированные
источники → метрики. Требует Ollama-эмбеддер + pgvector; skip, если недоступны. Числа
демонстративны (малый корпус), поэтому ассерты мягкие — проверяем, что поиск реально
попадает в релевантное, а не конкретную величину.
"""

from __future__ import annotations

import psycopg
import pytest

from app.adapters.embedder.ollama_embed import OllamaEmbedder
from app.adapters.vectorstore.pgvector_store import PgVectorStore
from app.config import get_settings
from app.eval.retrieval import mrr, ndcg_at_k, recall_at_k
from app.eval.retrieval_gold import GOLD
from app.rag.classify import build_classifier
from app.rag.ingest import collect_vendored_corpus, ingest
from app.rag.retrieve import hybrid_retrieve


@pytest.mark.integration
def test_retrieval_quality_on_gold_set() -> None:
    settings = get_settings()
    try:
        psycopg.connect(settings.database_url, autocommit=True, connect_timeout=3).close()
    except psycopg.OperationalError:
        pytest.skip("Postgres недоступен — подними docker compose up")

    embedder = OllamaEmbedder(
        settings.embed_model, base_url=settings.ollama_base_url, dimension=settings.embed_dimension
    )
    try:
        embedder.embed(["probe"])
    except Exception:
        pytest.skip("Ollama недоступен — эмбеддер не отвечает")

    store = PgVectorStore(settings.database_url, dimension=settings.embed_dimension)
    try:
        ingest(collect_vendored_corpus(), embedder, store, build_classifier(settings, embedder))
        ndcgs: list[float] = []
        recalls: list[float] = []
        mrrs: list[float] = []
        for query, relevant in GOLD:
            results = hybrid_retrieve(query, embedder, store, top_k=5)
            ranked = list(dict.fromkeys(rc.chunk.source for rc in results))  # dedup, порядок цел
            ndcgs.append(ndcg_at_k(ranked, set(relevant), 5))
            recalls.append(recall_at_k(ranked, set(relevant), 5))
            mrrs.append(mrr(ranked, set(relevant)))
        n = len(GOLD)
        # мягко: поиск реально находит релевантное (не точная величина на малом корпусе).
        assert sum(recalls) / n >= 0.7
        assert sum(ndcgs) / n >= 0.5
        assert sum(mrrs) / n >= 0.4  # baseline ~0.57; ловит просадку ранжирования
    finally:
        store.close()
