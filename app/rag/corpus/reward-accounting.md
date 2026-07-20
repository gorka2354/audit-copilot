# Reward accounting

## Что это
Ошибки в учёте наград стейкинга/фарминга: неверный порядок обновления
checkpoint'а, дрейф аккумулятора `rewardPerToken`, возможность двойного клейма —
пользователь забирает больше, чем начислено, за счёт остальных.

## Как возникает
- Изменение стейка до обновления накопленной награды (checkpoint drift).
- Аккумулятор `rewardPerTokenStored` обновляется не на всех путях.
- Нет обнуления `rewards[user]` после выплаты → double-claim.

## Признаки в коде
- reward/accounting без `updateReward` модификатора на всех входах;
- checkpoint обновляется после изменения баланса, а не до;
- claim без сброса начисленного — double-claim.

## Как чинить
- Модификатор `updateReward(account)` на stake/withdraw/claim — до изменения стейка.
- Единый аккумулятор `rewardPerToken`, обновляемый на каждом входе.
- Обнулять начисленное в момент выплаты.

## Пример
```solidity
function stake(uint256 amt) external { // забыли updateReward ДО изменения стейка
    balances[msg.sender] += amt;        // checkpoint drift → неверная награда
    totalStaked += amt;
}
```
