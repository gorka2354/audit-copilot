// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Корректная арифметика долей: умножение до деления, проверенный downcast.
/// Заведомо корректный контракт — любое срабатывание детектора здесь = false positive.
contract CheckedMath {
    function shareOf(uint256 amount, uint256 total, uint256 pool) external pure returns (uint256) {
        require(total > 0, "zero total");
        return (amount * pool) / total; // умножаем ДО деления — без потери точности
    }

    function toUint128(uint256 value) external pure returns (uint128) {
        require(value <= type(uint128).max, "overflow"); // проверенный downcast
        return uint128(value);
    }
}
