# Eval — defivulnlabs

## Детекторы (recall — три честных знаменателя)
- покрыто классов: 34 / 53 (+5 blind-spot: класс есть, детектора нет)
- recall covered: 71% [54%, 83%]  (24/34) — по классам, что движок умеет ловить
- recall +blind:  62% [46%, 75%]  (24/39) — включая непокрытые классы (для пользователя это тоже промах)
- recall корпус:  45% [33%, 59%]  (24/53) — по всем репро корпуса

### Промахи (детектор ожидался, но не сработал)
- Array-deletion.sol — ожидалось ['delmap'], сработало ['access', 'disabled']
- Precision-loss.sol — ожидалось ['precision'], сработало ['access', 'disabled']
- Price_manipulation.sol — ожидалось ['oracle'], сработало ['access', 'arbcall', 'precision', 'pyth', 'reentrancy', 'sibling', 'supply', 'unchecked']
- ReadOnlyReentrancy.sol — ожидалось ['roreentrancy'], сработало ['access', 'feeontransfer', 'reentrancy', 'spotoracle', 'unchecked']
- Unprotected-callback.sol — ожидалось ['access'], сработало ['supply']
- Visibility.sol — ожидалось ['access'], сработало ∅
- fee-on-transfer.sol — ожидалось ['feeontransfer'], сработало ['access', 'disabled', 'reentrancy', 'unchecked']
- first-deposit.sol — ожидалось ['erc4626'], сработало ['access', 'disabled', 'reentrancy', 'sibling', 'supply', 'unchecked']
- return-break.sol — ожидалось ['unchecked'], сработало ['access', 'disabled']
- unsafe-downcast.sol — ожидалось ['downcast'], сработало ['access', 'disabled']

## Precision (false-positive rate на заведомо чистых контрактах)
- чистых контрактов: 6
- с ложным срабатыванием: 4/6 (67%)
- среднее ложных флагов: 1.00 на контракт
