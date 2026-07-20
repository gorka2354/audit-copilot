# Signature replay

## Что это
Подпись, задуманная как одноразовое разрешение, принимается повторно — на другой
транзакции, в другом контракте или в другой сети — потому что в подписанные
данные не включён nonce, срок, адрес контракта или chainId.

## Как возникает
- Нет nonce → одну подпись предъявляют многократно.
- Нет domain separator (EIP-712) → подпись валидна в другом контракте/сети.
- `ecrecover` без проверки на нулевой адрес и malleability.

## Признаки в коде
- ecrecover/signature без nonce и срока действия;
- отсутствие EIP-712 domain separator (eip712);
- отсутствие проверки chainId; ERC-1271 для контрактных подписантов не учтён.

## Как чинить
- EIP-712 с domain separator (chainId + verifyingContract) и per-user nonce.
- Срок действия (deadline) в подписанных данных.
- Проверка `signer != address(0)`; поддержка ERC-1271 для смарт-кошельков.

## Пример
```solidity
// нет nonce, нет domain separator — replay на другой сети/контракте
address signer = ecrecover(keccak256(abi.encodePacked(to, amount)), v, r, s);
require(signer == owner);
```
