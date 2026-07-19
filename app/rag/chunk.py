"""Чанкинг документов для RAG.

Режем текст на перекрывающиеся фрагменты, стараясь сохранять границы абзацев
(markdown-корпус: паттерны уязвимостей, логи ханьтов). Слишком длинные абзацы
режутся жёстко. `overlap` сохраняет контекст между соседними чанками.
"""

from __future__ import annotations

from app.domain.rag import Chunk


def chunk_text(text: str, source: str, *, max_chars: int = 1200, overlap: int = 150) -> list[Chunk]:
    """Разбить текст на чанки. Каждый чанк ≤ ``max_chars + overlap`` — на границе
    абзацев к новому чанку может приклеиться overlap-хвост предыдущего.
    """
    if not 0 <= overlap < max_chars:
        raise ValueError(f"overlap ({overlap}) должен быть в [0, max_chars) = [0, {max_chars})")
    parts = _pack_paragraphs(text.strip(), max_chars=max_chars, overlap=overlap)
    return [Chunk(id=f"{source}#{i}", source=source, content=part) for i, part in enumerate(parts)]


def _pack_paragraphs(text: str, *, max_chars: int, overlap: int) -> list[str]:
    if not text:
        return []
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out: list[str] = []
    buf = ""
    for para in paragraphs:
        # абзац длиннее лимита — режем жёстко, предварительно сбросив буфер
        while len(para) > max_chars:
            if buf:
                out.append(buf)
                buf = ""
            out.append(para[:max_chars])
            para = para[max_chars - overlap :]
        if buf and len(buf) + len(para) + 2 > max_chars:
            out.append(buf)
            buf = (buf[-overlap:] + "\n\n" + para) if overlap else para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf.strip():
        out.append(buf)
    return [c.strip() for c in out if c.strip()]
