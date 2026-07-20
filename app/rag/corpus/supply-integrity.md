# Token supply integrity

## Что это
Нарушение инвариантов эмиссии: неограниченный или недостаточно защищённый `mint`,
рассинхрон между `totalSupply` и реальными балансами, двойной учёт при burn.
Итог — инфляция предложения и обесценивание токена.

## Как возникает
- `mint` без ограничения прав или лимита (unprotected mint).
- Обновление баланса без обновления `totalSupply` (или наоборот).
- Fee-on-transfer/rebasing токены ломают наивный учёт полученной суммы.

## Признаки в коде
- mint/burn без access-guard или supply-инварианта;
- totalSupply integrity: баланс меняется мимо totalSupply;
- inflation через повторный или неограниченный выпуск.

## Как чинить
- Гейтить mint ролью, фиксировать max supply.
- Держать `totalSupply` и сумму балансов согласованными в одной операции.
- Мерить фактически полученную сумму (balance delta) для fee-on-transfer.

## Пример
```solidity
function mint(address to, uint256 amt) external { // нет access control — произвольная эмиссия
    balanceOf[to] += amt;
    totalSupply += amt;
}
```
