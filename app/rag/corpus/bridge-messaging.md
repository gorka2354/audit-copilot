# Cross-chain bridge messaging

## Что это
Уязвимости моста/кросс-чейн сообщений: приём сообщения от непроверенного
отправителя, отсутствие защиты от повторной доставки, доверие к значению по
умолчанию у неинициализированного mapping'а маршрутов.

## Как возникает
- `lzReceive`/обработчик без проверки source chain и trusted remote.
- Нет учёта доставленных сообщений (replay доставки).
- mapping default value: непрописанный маршрут читается как 0/адрес(0) и трактуется как валидный.

## Признаки в коде
- cross-chain/LayerZero-хендлер без проверки отправителя (trusted remote);
- отсутствие nonce/учёта доставки сообщения;
- mapping default: доверие к нулевому значению непроинициализированного маршрута.

## Как чинить
- Проверять source chainId и trusted remote перед обработкой.
- Идемпотентность по nonce сообщения (учёт доставленных).
- Явная валидация маршрута; не полагаться на mapping default value.

## Пример
```solidity
function lzReceive(uint16 srcChain, bytes calldata src, ...) external {
    // нет проверки trustedRemote[srcChain] == src — приём от кого угодно
    _credit(abi.decode(payload, (address)), amount);
}
```
