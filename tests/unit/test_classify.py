"""Юнит-тесты keyword-классификатора класса уязвимости."""

from __future__ import annotations

from app.rag.classify import KNOWN_CLASSES, classify_chunk


def test_reentrancy_detected() -> None:
    assert classify_chunk("external call before state write, no nonReentrant (CEI)") == "reentrancy"


def test_oracle_detected() -> None:
    assert classify_chunk("Chainlink price feed without staleness check on updatedAt") == "oracle"


def test_access_detected() -> None:
    assert classify_chunk("unprotected privileged setter, no onlyOwner modifier") == "access"


def test_unrelated_is_general() -> None:
    assert classify_chunk("a note about documentation and the testing pyramid") == "general"


def test_result_is_always_a_known_class() -> None:
    assert classify_chunk("mixed reentrancy oracle mint ecrecover text") in KNOWN_CLASSES
