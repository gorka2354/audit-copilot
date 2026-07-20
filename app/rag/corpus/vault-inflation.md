# ERC-4626 vault share inflation

## Что это
Атака первого вкладчика (first depositor) на ERC-4626-хранилище: первый минтит
1 wei доли, «дарит» токены напрямую в vault, раздувая цену доли, и последующие
вкладчики получают 0 долей из-за округления вниз — их депозит достаётся атакующему.

## Как возникает
- Пустое хранилище: `shares = assets * totalSupply / totalAssets` при `totalSupply=0`.
- Прямой перевод токенов в vault раздувает `totalAssets` мимо `totalSupply`.
- Округление вниз в share math обнуляет доли жертвы.

## Признаки в коде
- ERC-4626 без «мёртвых» долей или начального депозита;
- share accounting math, чувствительная к прямому донату в vault;
- отсутствие виртуальных offset-долей (OpenZeppelin ERC4626 decimals offset).

## Как чинить
- Виртуальные доли/активы (decimals offset) — дефолт OZ ERC4626.
- Минт «мёртвых» долей при первом депозите (seed).
- Не полагаться на `balanceOf(vault)` как на totalAssets.

## Пример
```solidity
// первый вкладчик: totalSupply=0 → 1 wei доля, затем донат раздувает цену доли
uint256 shares = totalSupply == 0 ? assets : assets * totalSupply / totalAssets;
```
