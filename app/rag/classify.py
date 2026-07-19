"""Классификация фрагмента по классу уязвимости (для class-фильтра RAG).

Два адаптера за портом `Classifier`:
- `KeywordClassifier` — детерминированная keyword-эвристика (дёшево, офлайн);
- `EmbeddingClassifier` (в `embedding_classifier.py`) — zero-shot по эмбеддингам.

`route_detector` маршрутизирует находку детектора в класс для RAG-фильтра.
"""

from __future__ import annotations

from app.config import Settings
from app.domain.ports import Classifier, Embedder

_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "reentrancy": ("reentran", "external call", "nonreentrant", "checks-effects", "cei"),
    "oracle": ("oracle", "chainlink", "price feed", "staleness", "spot price", "twap", "pyth"),
    "access": ("access control", "onlyowner", "unprotected", "privileged", "ungated", "authoriz"),
    "supply": ("mint", "burn", "totalsupply", "inflation", "supply integrity"),
    "precision": (
        "precision",
        "rounding",
        "decimal",
        "divide before multiply",
        "downcast",
        "overflow",
    ),
    "signature": (
        "ecrecover",
        "signature",
        "eip-712",
        "eip712",
        "replay",
        "domain separator",
        "erc-1271",
    ),
    "vault": ("erc4626", "erc-4626", "first depositor", "share math", "vault share"),
    "reward": ("reward", "checkpoint", "double-claim", "accounting"),
    "bridge": ("bridge", "layerzero", "cross-chain", "crosschain", "mapping default"),
}

KNOWN_CLASSES = frozenset(_CLASS_KEYWORDS) | {"general"}

# Семантические описания классов — прототипы для zero-shot EmbeddingClassifier.
CLASS_DESCRIPTIONS: dict[str, str] = {
    "reentrancy": "reentrancy: external call before the state write, missing nonReentrant, "
    "checks-effects-interactions violation",
    "oracle": "price oracle manipulation, stale Chainlink feed, spot AMM price, missing TWAP",
    "access": "missing access control, unprotected privileged setter, no onlyOwner or auth guard",
    "supply": "token supply integrity, unchecked mint or burn, totalSupply inflation",
    "precision": "precision loss, rounding, divide before multiply, unsafe downcast, overflow",
    "signature": "signature replay, ecrecover misuse, EIP-712 domain separator, ERC-1271",
    "vault": "ERC-4626 vault, first depositor share inflation, share accounting math",
    "reward": "reward accounting, checkpoint drift, double-claim of rewards",
    "bridge": "cross-chain bridge, LayerZero messaging, default mapping value",
}


class KeywordClassifier:
    """`Classifier` на keyword-эвристике: класс с наибольшим числом совпадений, иначе `general`."""

    def classify(self, text: str) -> str:
        low = text.lower()
        best_class, best_hits = "general", 0
        for vuln_class, keywords in _CLASS_KEYWORDS.items():
            hits = sum(low.count(kw) for kw in keywords)
            if hits > best_hits:
                best_class, best_hits = vuln_class, hits
        return best_class


def route_detector(
    classifier: Classifier, detector: str, title: str = "", note: str = ""
) -> str | None:
    """Класс для маршрутизации находки в RAG, иначе `None` (искать по всей базе).

    `None` (а не `general`) означает «класс не распознан» — retrieve не сужается до
    общих заметок, а идёт по всему корпусу.
    """
    guess = classifier.classify(f"{detector} {title} {note}")
    return guess if guess != "general" else None


def build_classifier(settings: Settings, embedder: Embedder) -> Classifier:
    """Собрать классификатор по `settings.classifier` (`keyword` | `embedding`)."""
    if settings.classifier == "keyword":
        return KeywordClassifier()
    if settings.classifier == "embedding":
        # lazy-import: embedding_classifier тянет CLASS_DESCRIPTIONS отсюда же
        from app.rag.embedding_classifier import EmbeddingClassifier

        return EmbeddingClassifier(embedder)
    raise ValueError(
        f"неизвестный classifier '{settings.classifier}'; допустимо: keyword | embedding"
    )
