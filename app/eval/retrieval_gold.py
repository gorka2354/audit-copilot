"""Независимый gold-set для оценки retrieval: запрос → релевантные документы корпуса.

Размечено ВРУЧНУЮ по смыслу, а не по `metadata.class`: релевантность каждой пары проставлена
человеком (какой паттерн реально отвечает на запрос), а не выведена из класса чанка — иначе
метрика мерила бы самосогласованность классификатора, не качество поиска.

Малый и иллюстративный (10 пар на корпусе из 9 документов): показывает МЕТОДОЛОГИЮ честной
оценки поиска. На таком корпусе recall@k насыщается (top-k вытягивает почти всё), поэтому
числа демонстративны — ценность в независимой разметке и в самих метриках, а не в величине.
"""

from __future__ import annotations

# (запрос своими словами, множество релевантных источников корпуса)
GOLD: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "the contract sends ether to the caller before it writes the new balance",
        frozenset({"corpus/reentrancy.md"}),
    ),
    (
        "any address can invoke the ownership setter and seize control of the contract",
        frozenset({"corpus/access-control.md"}),
    ),
    (
        "a flash loan skews the pool reserves that feed the lending price",
        frozenset({"corpus/price-oracle.md"}),
    ),
    (
        "dividing before multiplying rounds the user payout down to zero",
        frozenset({"corpus/precision-loss.md"}),
    ),
    (
        "the same signed message is accepted twice because nothing tracks a nonce",
        frozenset({"corpus/signature-replay.md"}),
    ),
    (
        "the first depositor mints one wei of shares then donates tokens to steal deposits",
        frozenset({"corpus/vault-inflation.md"}),
    ),
    (
        "tokens can be issued without limit because issuance has no owner restriction",
        frozenset({"corpus/supply-integrity.md", "corpus/access-control.md"}),
    ),
    (
        "staking rewards are collected twice because the accrual snapshot is stale",
        frozenset({"corpus/reward-accounting.md"}),
    ),
    (
        "a message handler trusts an unverified remote sender from another chain",
        frozenset({"corpus/bridge-messaging.md"}),
    ),
    (
        "narrowing a large integer into a smaller type silently truncates the value",
        frozenset({"corpus/precision-loss.md"}),
    ),
)
