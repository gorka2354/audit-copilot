# Access control

## Что это
Отсутствие или неверная проверка прав доступа: привилегированная функция (смена
владельца, вывод средств, апгрейд, пауза) вызывается кем угодно, потому что нет
`onlyOwner`, роли или иной authorization-проверки.

## Как возникает
- Забыли модификатор на setter'е (`setOwner`, `setFeeTo`, `initialize`).
- `public`/`external` вместо `internal` на чувствительной функции.
- Неинициализированный владелец после деплоя (front-run `initialize`).

## Признаки в коде
- privileged setter без `onlyOwner`/`onlyRole`;
- ungated `initialize` без защиты от повторного вызова;
- отсутствие authorization guard на функции, меняющей критичное состояние.

## Как чинить
- `onlyOwner`/`AccessControl` роли (OpenZeppelin) на всех привилегированных путях.
- `initializer` modifier против повторной инициализации.
- Принцип наименьших привилегий; двухшаговая передача владения.

## Пример
```solidity
address public owner;
function setOwner(address o) external { // нет onlyOwner — любой перехватит владение
    owner = o;
}
```
