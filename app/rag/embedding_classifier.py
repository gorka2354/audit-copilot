"""Zero-shot классификатор по эмбеддингам: класс с ближайшим семантическим прототипом.

Альтернатива `KeywordClassifier` за тем же портом `Classifier`. Прототипы классов
(эмбеддинги `CLASS_DESCRIPTIONS`) считаются один раз при инициализации; классификация
текста — эмбеддинг + косинус к прототипам, argmax. Ниже порога близости → `general`
(класс не распознан уверенно), как и у keyword-эвристики.

Точнее keyword на перефразировках («ownership takeover» → access), но дороже: на каждую
классификацию идёт сетевой вызов эмбеддера. Оба варианта за портом — выбор через конфиг.
"""

from __future__ import annotations

from app.domain.ports import Embedder
from app.rag.classify import CLASS_DESCRIPTIONS


class EmbeddingClassifier:
    """`Classifier` через эмбеддинги: косинус текста к прототипам классов."""

    def __init__(self, embedder: Embedder, *, threshold: float = 0.3) -> None:
        self._embedder = embedder
        self._threshold = threshold
        self._classes = list(CLASS_DESCRIPTIONS)
        self._prototypes = embedder.embed(list(CLASS_DESCRIPTIONS.values()))

    def classify(self, text: str) -> str:
        vectors = self._embedder.embed([text])
        if not vectors:
            return "general"
        query = vectors[0]
        best_class, best_sim = "general", self._threshold
        for vuln_class, prototype in zip(self._classes, self._prototypes, strict=True):
            sim = _cosine(query, prototype)
            if sim > best_sim:
                best_class, best_sim = vuln_class, sim
        return best_class


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
