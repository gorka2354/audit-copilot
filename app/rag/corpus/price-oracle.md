# Price oracle manipulation

## Что это
Протокол берёт цену из манипулируемого источника — спотовой цены AMM-пула или
устаревшего фида — и злоумышленник искажает её (flash-loan swap), чтобы занять,
ликвидировать или вывести больше положенного.

## Как возникает
- Спотовая цена из `getReserves()`/`slot0` одного пула как источник истины.
- Chainlink-фид без проверки staleness (`updatedAt`, `answeredInRound`).
- Отсутствие TWAP и sanity-границ на цену.

## Признаки в коде
- price feed из спотового резерва AMM (spot price) без TWAP;
- `latestAnswer`/`latestRoundData` без проверки свежести (staleness);
- нет отклонения на аномальную цену от Chainlink/Pyth.

## Как чинить
- TWAP или несколько независимых оракулов, медиана.
- Проверять `updatedAt` и допустимый интервал (staleness guard).
- Границы на резкое отклонение цены между обновлениями.

## Пример
```solidity
// спотовая цена одного пула — манипулируется flash-loan swap
uint256 price = reserve1 * 1e18 / reserve0; // нет TWAP, нет staleness
```
