"""LLM-реранк кандидатов RAG по релевантности запросу.

Best-effort: при неразборчивом ответе или транзиентном сбое LLM возвращаем
исходный порядок (реранк не критичен — гибрид уже дал разумное ранжирование).
Исключение — жёсткие сигналы: исчерпанный бюджет и терминальные ошибки провайдера
пробрасываются, чтобы `/search?rerank=true` отдавал 429/502, а не тихую 200.
"""

from __future__ import annotations

import json
import re

from app.domain.llm import LLMError, Message, Role
from app.domain.ports import LLMProvider
from app.domain.rag import RetrievedChunk
from app.observability.budget import BudgetExceeded


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
    except BudgetExceeded:
        raise  # бюджет — жёсткий стоп, не глушим в исходный порядок
    except LLMError as exc:
        if not exc.retryable:
            raise  # терминальная ошибка провайдера — не маскируем
        return candidates[:top_k]  # транзиентная — реранк опустим
    except Exception:  # прочее — реранк best-effort, откатываем к исходному порядку
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
