"""Размеченный корпус для eval: контракт → ожидаемый класс уязвимости.

Источник — DeFiVulnLabs (SunWeb3Sec, MIT): 53 самодостаточных репро, класс
уязвимости закодирован в имени файла. Vendored в `assets/eval/defivulnlabs/`
(работает вхолодную, без security-lab; 4 UNLICENSED-файла исходного репо
исключены — см. `SOURCE.md`). Таблица
`_BENCH` (keyword → ожидаемые `det_key`) — это выверенная разметка из
`toolkit/shadow.py`; переиспользуем её как ground-truth (данные, не логику).

`expected_detectors` пуст, когда класс не покрыт детекторами recon (blind spot)
или имя не размечено — такие кейсы честно исключаются из знаменателя recall.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.domain.models import SoliditySource

# Vendored eval-корпус в репозитории (см. assets/eval/defivulnlabs/SOURCE.md).
# parents[2] от app/eval/corpus.py — корень репозитория.
_VENDORED_DIR = Path(__file__).resolve().parents[2] / "assets" / "eval" / "defivulnlabs"
# Заведомо чистые контракты для измерения false-positive rate.
_CLEAN_DIR = Path(__file__).resolve().parents[2] / "assets" / "eval" / "clean"


def load_clean_sources() -> list[SoliditySource]:
    """Заведомо чистые контракты (любое срабатывание детектора на них = false positive)."""
    return [
        SoliditySource(path=p.name, code=p.read_text(encoding="utf-8", errors="ignore"))
        for p in sorted(_CLEAN_DIR.glob("*.sol"))
    ]

# keyword в нормализованном имени файла → ожидаемые det_key recon (None = blind spot).
# Порядок важен: более специфичные keyword идут первыми (первое совпадение выигрывает).
_BENCH: tuple[tuple[str, frozenset[str] | None], ...] = (
    ("read-only-reentrancy", frozenset({"roreentrancy"})),
    ("readonlyreentrancy", frozenset({"roreentrancy"})),
    ("reentrancy", frozenset({"reentrancy", "nftcallback"})),
    ("unsafe-downcast", frozenset({"downcast"})),
    ("downcast", frozenset({"downcast"})),
    ("divide-before-multiply", frozenset({"precision"})),
    ("divmultiply", frozenset({"precision"})),
    ("precision-loss", frozenset({"precision"})),
    ("precision", frozenset({"precision"})),
    ("abi-encodepacked", frozenset({"encodepacked"})),
    ("encodepacked", frozenset({"encodepacked"})),
    ("hash-collision", frozenset({"encodepacked"})),
    ("fee-on-transfer", frozenset({"feeontransfer"})),
    ("deflation", frozenset({"feeontransfer"})),
    ("signature-replay", frozenset({"signature"})),
    ("signature", frozenset({"signature"})),
    ("replay", frozenset({"signature"})),
    ("ecdsa", frozenset({"signature"})),
    ("ecrecover", frozenset({"signature"})),
    ("array-deletion", frozenset({"delmap"})),
    ("struct-deletion", frozenset({"delmap"})),
    ("deletion", frozenset({"delmap"})),
    ("delete", frozenset({"delmap"})),
    ("unsafecall", frozenset({"arbcall", "danger"})),
    ("storage-collision", None),  # proxy slot collision — reasoning-tier
    ("storagecollision", None),
    ("unsafe-delegatecall", frozenset({"danger", "arbcall"})),
    ("delegatecall", frozenset({"danger", "arbcall"})),
    ("selfdestruct", frozenset({"danger"})),
    ("tx-origin", frozenset({"danger"})),
    ("txorigin", frozenset({"danger"})),
    ("access-control", frozenset({"access", "sibling"})),
    ("accesscontrol", frozenset({"access", "sibling"})),
    ("visibility", frozenset({"access"})),
    ("unprotected", frozenset({"access"})),
    ("unchecked-return", frozenset({"unchecked"})),
    ("unchecked", frozenset({"unchecked"})),
    ("return-value", frozenset({"unchecked"})),
    ("returnvalue", frozenset({"unchecked"})),
    ("returnfalse", frozenset({"unchecked"})),
    ("return-break", frozenset({"unchecked"})),
    ("weak-random", frozenset({"weakrand"})),
    ("random", frozenset({"weakrand"})),
    ("price-oracle", frozenset({"oracle"})),
    ("price-manipulation", frozenset({"oracle"})),
    ("oracle", frozenset({"oracle"})),
    ("slippage", frozenset({"swapguard"})),
    ("sandwich", frozenset({"swapguard"})),
    ("first-deposit", frozenset({"erc4626"})),
    ("vault-inflation", frozenset({"erc4626"})),
    ("erc4626", frozenset({"erc4626"})),
    ("inflation", frozenset({"erc4626"})),
    ("uninitialized", frozenset({"upgrade", "danger"})),
    ("phantom", None),  # fallback-permit phantom fn — uncovered
    ("flashloan", frozenset({"flashloan"})),
    ("erc777", None),  # tokensReceived callback — uncovered
    ("self-transfer", frozenset({"selftransfer"})),
    ("transient", None),  # EIP-1153 misuse — uncovered
    ("dos", None),  # generic DoS — uncovered
    ("overflow", frozenset({"overflow"})),
    ("underflow", frozenset({"overflow"})),
    ("bypass-contract", frozenset({"l2"})),
    ("bypasscontract", frozenset({"l2"})),
)


@dataclass(frozen=True, slots=True)
class EvalCase:
    """Один размеченный пример: контракт + ожидаемые детекторы."""

    name: str
    source: SoliditySource
    vuln_class: str
    """Сопоставленный keyword класса уязвимости (или `unmapped`)."""

    expected_detectors: frozenset[str]
    """Ожидаемые `det_key`; пусто — класс не покрыт recon либо имя не размечено."""

    @property
    def is_covered(self) -> bool:
        """Есть ожидаемый детектор → кейс участвует в знаменателе recall."""
        return bool(self.expected_detectors)


@runtime_checkable
class EvalCorpus(Protocol):
    """Источник размеченных примеров для eval — взаимозаменяемый за портом."""

    name: str

    def cases(self) -> list[EvalCase]:
        """Загрузить все размеченные примеры корпуса."""
        ...


def normalize_name(filename: str) -> str:
    """Имя файла → lowercase-slug: отбросить каталог/расширение, разделители → `-`."""
    base = Path(filename).name.rsplit(".", 1)[0].lower()
    for ch in ("_", " ", "."):
        base = base.replace(ch, "-")
    return base


def expected_for_slug(slug: str) -> tuple[str, frozenset[str]]:
    """`(keyword, ожидаемые det_key)` для slug; `('unmapped', frozenset())`, если нет совпадений."""
    for keyword, keys in _BENCH:
        if keyword in slug:
            return keyword, (keys or frozenset())
    return "unmapped", frozenset()


class DeFiVulnLabsCorpus:
    """`EvalCorpus` поверх DeFiVulnLabs — класс уязвимости из имени файла."""

    name = "defivulnlabs"
    _SUBPATH = ("cache", "DeFiVulnLabs", "src", "test")

    def __init__(self, test_dir: Path) -> None:
        self._test_dir = test_dir

    @classmethod
    def from_security_lab(cls, security_lab_path: Path) -> DeFiVulnLabsCorpus:
        return cls(security_lab_path.joinpath(*cls._SUBPATH))

    @classmethod
    def vendored(cls) -> DeFiVulnLabsCorpus:
        """Корпус из vendored-ассетов репозитория — работает вхолодную, без security-lab."""
        return cls(_VENDORED_DIR)

    def cases(self) -> list[EvalCase]:
        cases: list[EvalCase] = []
        for path in sorted(self._test_dir.glob("*.sol")):
            slug = normalize_name(path.name)
            vuln_class, expected = expected_for_slug(slug)
            # errors="ignore" — паритет с recon, чтобы не падать на не-utf8
            code = path.read_text(encoding="utf-8", errors="ignore")
            cases.append(
                EvalCase(
                    name=path.name,
                    source=SoliditySource(path=path.name, code=code),
                    vuln_class=vuln_class,
                    expected_detectors=expected,
                )
            )
        return cases
