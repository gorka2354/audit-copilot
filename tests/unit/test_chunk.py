"""Юнит-тесты чанкера."""

from __future__ import annotations

import pytest

from app.rag.chunk import chunk_text


def test_rejects_overlap_ge_max_chars() -> None:
    # overlap >= max_chars раньше вешал hard-split в бесконечный цикл
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("x" * 100, "s", max_chars=50, overlap=50)
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("x" * 100, "s", max_chars=50, overlap=60)


def test_empty_text_no_chunks() -> None:
    assert chunk_text("", "s") == []
    assert chunk_text("   \n\n  ", "s") == []


def test_short_text_single_chunk() -> None:
    chunks = chunk_text("Один короткий абзац про reentrancy.", "doc.md")
    assert len(chunks) == 1
    assert chunks[0].id == "doc.md#0"
    assert chunks[0].source == "doc.md"
    assert "reentrancy" in chunks[0].content


def test_long_text_splits_and_numbers_ids() -> None:
    text = "\n\n".join(f"Абзац {i} " * 25 for i in range(10))
    chunks = chunk_text(text, "big.md", max_chars=500, overlap=50)
    assert len(chunks) > 1
    assert [c.id for c in chunks] == [f"big.md#{i}" for i in range(len(chunks))]
    # каждый чанк в пределах лимита плюс допуск на overlap-хвост
    assert all(len(c.content) <= 500 + 50 for c in chunks)


def test_oversized_paragraph_hard_split() -> None:
    chunks = chunk_text("x" * 2000, "d", max_chars=500, overlap=50)
    assert len(chunks) >= 4
    assert all(len(c.content) <= 500 for c in chunks)
