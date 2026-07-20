// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Безопасное хранилище: checks-effects-interactions + guard от reentrancy.
/// Заведомо корректный контракт — любое срабатывание детектора здесь = false positive.
contract SafeVault {
    mapping(address => uint256) private balances;
    uint256 private locked;

    modifier nonReentrant() {
        require(locked == 0, "reentrant");
        locked = 1;
        _;
        locked = 0;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw(uint256 amount) external nonReentrant {
        require(balances[msg.sender] >= amount, "insufficient");
        balances[msg.sender] -= amount; // эффект ДО взаимодействия (CEI)
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "transfer failed");
    }
}
