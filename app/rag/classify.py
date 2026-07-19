"""Грубая классификация фрагмента по классу уязвимости (для фильтра RAG).

Детерминированная keyword-эвристика: у чанка — один primary-класс (или `general`),
чтобы retrieve мог сузить контекст до релевантного семейства уязвимостей.
"""

from __future__ import annotations

_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "reentrancy": ("reentran", "external call", "nonreentrant", "checks-effects", "cei"),
    "oracle": ("oracle", "chainlink", "price feed", "staleness", "spot price", "twap", "pyth"),
    "access": ("access control", "onlyowner", "unprotected", "privileged", "ungated", "authoriz"),
    "supply": ("mint", "burn", "totalsupply", "inflation", "supply integrity"),
    "precision": (
        "precision", "rounding", "decimal", "divide before multiply", "downcast", "overflow",
    ),
    "signature": (
        "ecrecover", "signature", "eip-712", "eip712", "replay", "domain separator", "erc-1271",
    ),
    "vault": ("erc4626", "erc-4626", "first depositor", "share math", "vault share"),
    "reward": ("reward", "checkpoint", "double-claim", "accounting"),
    "bridge": ("bridge", "layerzero", "cross-chain", "crosschain", "mapping default"),
}

KNOWN_CLASSES = frozenset(_CLASS_KEYWORDS) | {"general"}


def classify_chunk(text: str) -> str:
    """Класс с наибольшим числом совпадений ключевых слов, иначе `general`."""
    low = text.lower()
    best_class, best_hits = "general", 0
    for vuln_class, keywords in _CLASS_KEYWORDS.items():
        hits = sum(low.count(kw) for kw in keywords)
        if hits > best_hits:
            best_class, best_hits = vuln_class, hits
    return best_class
