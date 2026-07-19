"""Юнит-тесты размеченного корпуса eval (на temp .sol фикстурах, без security-lab)."""

from __future__ import annotations

from pathlib import Path

from app.eval.corpus import (
    DeFiVulnLabsCorpus,
    EvalCorpus,
    expected_for_slug,
    normalize_name,
)


def test_normalize_name_slugifies() -> None:
    assert normalize_name("ERC777-reentrancy.sol") == "erc777-reentrancy"
    assert normalize_name("Precision_loss.sol") == "precision-loss"


def test_expected_for_slug_maps_known_class() -> None:
    assert expected_for_slug("precision-loss") == ("precision-loss", frozenset({"precision"}))
    keyword, keys = expected_for_slug("access-control")
    assert keyword == "access-control"
    assert keys == frozenset({"access", "sibling"})


def test_expected_for_slug_blind_spot_is_empty() -> None:
    # storage-collision размечен как blind spot (recon не покрывает) → keyword есть, det пусто
    assert expected_for_slug("storage-collision") == ("storage-collision", frozenset())


def test_expected_for_slug_unmapped() -> None:
    assert expected_for_slug("totally-unknown-thing") == ("unmapped", frozenset())


def test_first_match_wins() -> None:
    # "erc777-reentrancy": reentrancy стоит в таблице раньше erc777 → выигрывает reentrancy
    keyword, keys = expected_for_slug("erc777-reentrancy")
    assert keyword == "reentrancy"
    assert "reentrancy" in keys


def test_bench_covers_regression_keywords() -> None:
    # регрессия: эти keyword ранее выпали при транскрипции; return-break скрывал реальный MISS
    assert expected_for_slug("divmultiply") == ("divmultiply", frozenset({"precision"}))
    assert expected_for_slug("returnfalse") == ("returnfalse", frozenset({"unchecked"}))
    assert expected_for_slug("return-break") == ("return-break", frozenset({"unchecked"}))


def test_corpus_loads_and_labels_cases(tmp_path: Path) -> None:
    (tmp_path / "Reentrancy.sol").write_text("contract R {}")
    (tmp_path / "storage-collision.sol").write_text("contract S {}")
    (tmp_path / "Weird-thing.sol").write_text("contract W {}")

    cases = {c.name: c for c in DeFiVulnLabsCorpus(tmp_path).cases()}

    assert cases["Reentrancy.sol"].expected_detectors == frozenset({"reentrancy", "nftcallback"})
    assert cases["Reentrancy.sol"].is_covered
    assert not cases["storage-collision.sol"].is_covered  # blind spot → вне знаменателя recall
    assert cases["Weird-thing.sol"].vuln_class == "unmapped"


def test_corpus_satisfies_port(tmp_path: Path) -> None:
    assert isinstance(DeFiVulnLabsCorpus(tmp_path), EvalCorpus)
