"""Ingest корпуса знаний по безопасности в векторное хранилище.

Источник — markdown из security-lab (паттерны уязвимостей + логи ханьтов).
Индексация идёт ПОДОКУМЕНТНО через `replace_source`: старые чанки документа
удаляются перед вставкой новых — это исключает orphan-чанки, когда документ
сжался или удалён из корпуса.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.domain.ports import Embedder, VectorStore
from app.rag.chunk import chunk_text
from app.rag.classify import classify_chunk

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
    overlap: int = 150,
) -> int:
    """Проиндексировать документы (подокументный replace); вернуть число чанков."""
    total = 0
    for source, text in docs:
        chunks = [
            replace(chunk, metadata={"class": classify_chunk(chunk.content)})
            for chunk in chunk_text(text, source, max_chars=max_chars, overlap=overlap)
        ]
        embeddings = _embed_all(embedder, [c.content for c in chunks]) if chunks else []
        store.replace_source(source, chunks, embeddings)
        total += len(chunks)
    return total


def _embed_all(embedder: Embedder, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH):
        out.extend(embedder.embed(texts[start : start + _EMBED_BATCH]))
    return out


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")
