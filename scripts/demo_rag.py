"""Демо Инкремента 2: RAG — индексация корпуса security-lab и семантический поиск.

    uv run python scripts/demo_rag.py --ingest "reentrancy in withdraw"
    uv run python scripts/demo_rag.py "spot price oracle manipulation"
"""

from __future__ import annotations

import argparse

from app.adapters.embedder.ollama_embed import OllamaEmbedder
from app.adapters.vectorstore.pgvector_store import PgVectorStore
from app.config import get_settings
from app.rag.ingest import collect_corpus, ingest
from app.rag.retrieve import retrieve


def main() -> int:
    parser = argparse.ArgumentParser(description="Демо RAG: индексация корпуса + поиск")
    parser.add_argument("query", nargs="?", default="reentrancy in withdraw")
    parser.add_argument(
        "--ingest", action="store_true", help="переиндексировать корпус security-lab"
    )
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    settings = get_settings()
    embedder = OllamaEmbedder(
        settings.embed_model, base_url=settings.ollama_base_url, dimension=settings.embed_dimension
    )
    store = PgVectorStore(settings.database_url, dimension=settings.embed_dimension)

    if args.ingest:
        docs = collect_corpus(settings.security_lab_path)
        count = ingest(docs, embedder, store)
        print(f"проиндексировано: {count} чанков из {len(docs)} документов\n")

    results = retrieve(args.query, embedder, store, top_k=args.top_k)
    print(f"запрос: {args.query}")
    print("═" * 60)
    for r in results:
        snippet = " ".join(r.chunk.content.split())[:220]
        print(f"[{r.score:.3f}] {r.chunk.source}")
        print(f"       {snippet}…\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
