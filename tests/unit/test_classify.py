"""Юнит-тесты keyword-классификатора и маршрутизации детектора."""

from __future__ import annotations

from app.rag.classify import KNOWN_CLASSES, KeywordClassifier, route_detector

_kw = KeywordClassifier()


def test_reentrancy_detected() -> None:
    assert _kw.classify("external call before state write, no nonReentrant (CEI)") == "reentrancy"


def test_oracle_detected() -> None:
    assert _kw.classify("Chainlink price feed without staleness check on updatedAt") == "oracle"


def test_access_detected() -> None:
    assert _kw.classify("unprotected privileged setter, no onlyOwner modifier") == "access"


def test_unrelated_is_general() -> None:
    assert _kw.classify("a note about documentation and the testing pyramid") == "general"


def test_result_is_always_a_known_class() -> None:
    assert _kw.classify("mixed reentrancy oracle mint ecrecover text") in KNOWN_CLASSES


def test_route_detector_routes_known_finding() -> None:
    assert route_detector(_kw, "access", "Missing access control") == "access"
    assert route_detector(_kw, "spotoracle", "Spot price oracle read") == "oracle"


def test_route_detector_returns_none_when_unrecognized() -> None:
    # неизвестный класс → None (RAG ищет по всей базе, а не сужается до general)
    assert route_detector(_kw, "misc", "some generic gas note") is None
