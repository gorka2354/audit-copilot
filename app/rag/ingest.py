"""Ingest корпуса знаний по безопасности в векторное хранилище.

Источник — markdown из security-lab (паттерны уязвимостей + логи ханьтов).
Читаем → чанкуем → эмбеддим батчами (на мини-ПК) → сохраняем в pgvector.
"""

from __future__ import annotations

from pathlib import Path

from app.domain.ports import Embedder, VectorStore
from app.rag.chunk import chunk_text

_EMBED_BATCH = 64


def collect_corpus(security_lab_path: Path) -> list[tuple[str, str]]:
    """Собрать пары (source, text): паттерны безопасности + логи ханьтов."""
    docs: list[tuple[str, str]] = []

    patterns = security_lab_path / "research" / "patterns"
    if patterns.is_dir():
        for md in sorted(patterns.glob("*.md")):
            docs.append((f"research/patterns/{md.name}", _read(md)))

    hunts = security_lab_path / "hunts"
    if hunts.is_dir():
        for hunt_md in sorted(hunts.glob("*/HUNT.md")):
            docs.append((str(hunt_md.relative_to(security_lab_path)), _read(hunt_md)))

    return docs


def ingest(
    docs: list[tuple[str, str]],
    embedder: Embedder,
    store: VectorStore,
    *,
    max_chars: int = 1200,
) -> int:
    """Проиндексировать документы; вернуть число сохранённых чанков."""
    chunks = [
        chunk
        for source, text in docs
        for chunk in chunk_text(text, source, max_chars=max_chars)
    ]
    for start in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[start : start + _EMBED_BATCH]
        embeddings = embedder.embed([chunk.content for chunk in batch])
        store.add(batch, embeddings)
    return len(chunks)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")
