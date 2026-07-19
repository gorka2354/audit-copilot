"""LLM-реранк кандидатов RAG по релевантности запросу.

Best-effort: при любой ошибке LLM или неразборчивом ответе возвращаем исходный
порядок (реранк не критичен — гибрид уже дал разумное ранжирование).
"""

from __future__ import annotations

import json
import re

from app.domain.llm import Message, Role
from app.domain.ports import LLMProvider
from app.domain.rag import RetrievedChunk


def llm_rerank(
    query: str, candidates: list[RetrievedChunk], llm: LLMProvider, *, top_k: int = 5
) -> list[RetrievedChunk]:
    if len(candidates) <= 1:
        return candidates[:top_k]

    listing = "\n".join(f"[{i}] {c.chunk.content[:300]}" for i, c in enumerate(candidates))
    prompt = (
        f"Query: {query}\n\nFragments:\n{listing}\n\n"
        f"Return a JSON array of the {top_k} most relevant fragment indices, most relevant "
        f"first, e.g. [3,0,5]. JSON only, no prose."
    )
    try:
        response = llm.generate([Message(Role.USER, prompt)], max_tokens=100)
    except Exception:  # реранк опционален — любой сбой откатывает к исходному порядку
        return candidates[:top_k]

    order = _parse_indices(response.text, len(candidates))
    seen: set[int] = set()
    ranked: list[RetrievedChunk] = []
    for i in order:
        if i not in seen:
            seen.add(i)
            ranked.append(candidates[i])
    ranked.extend(c for i, c in enumerate(candidates) if i not in seen)  # добить остальными
    return ranked[:top_k]


def _parse_indices(text: str, n: int) -> list[int]:
    match = re.search(r"\[[\d,\s]*\]", text)
    if not match:
        return list(range(n))
    try:
        raw = json.loads(match.group())
    except ValueError:
        return list(range(n))
    return [i for i in raw if isinstance(i, int) and 0 <= i < n]
