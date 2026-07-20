# Reentrancy

## Что это
Reentrancy возникает, когда контракт делает внешний вызов (external call) до того,
как обновит собственное состояние. Вызываемый контракт может повторно войти
(re-enter) в исходную функцию и увидеть устаревшее состояние — например, снять
баланс несколько раз до его списания.

## Как возникает
Нарушение порядка checks-effects-interactions (CEI): сначала перевод средств,
потом запись состояния. Классика — `withdraw`, который шлёт эфир через
`msg.sender.call{value: ...}` и только затем обнуляет баланс. Read-only reentrancy
бьёт по view-функциям, которые читают согласованное на середине состояние.

## Признаки в коде
- external call (`call`, `transfer`, `send`, низкоуровневый `call{value:}`) перед записью в storage;
- отсутствие модификатора `nonReentrant`;
- перевод средств до обновления `balances[...]`.

## Как чинить
- Порядок CEI: сначала эффекты (запись состояния), потом interactions (внешний вызов).
- Reentrancy guard (`nonReentrant`, OpenZeppelin `ReentrancyGuard`).
- Pull-over-push для вывода средств.

## Пример
```solidity
function withdraw(uint256 amount) external {
    require(balances[msg.sender] >= amount);
    (bool ok, ) = msg.sender.call{value: amount}(""); // external call ПЕРЕД записью
    require(ok);
    balances[msg.sender] -= amount;                   // состояние обновлено ПОЗЖЕ — reentrancy
}
```
