// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Административные функции под onlyOwner с двухшаговой передачей владения.
/// Заведомо корректный контракт — любое срабатывание детектора здесь = false positive.
contract TimelockAdmin {
    address public owner;
    address public pendingOwner;

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    function proposeOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "zero owner");
        pendingOwner = newOwner;
    }

    function acceptOwnership() external {
        require(msg.sender == pendingOwner, "not pending");
        owner = pendingOwner;
        pendingOwner = address(0);
    }
}
