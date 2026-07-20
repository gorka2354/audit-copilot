// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Токен с корректным access control: mint только владельцем, с потолком (cap).
/// Заведомо корректный контракт — любое срабатывание детектора здесь = false positive.
contract OwnableToken {
    address public owner;
    uint256 public totalSupply;
    uint256 public immutable cap;
    mapping(address => uint256) public balanceOf;

    constructor(uint256 cap_) {
        owner = msg.sender;
        cap = cap_;
    }

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    function mint(address to, uint256 amount) external onlyOwner {
        require(totalSupply + amount <= cap, "cap exceeded");
        totalSupply += amount;
        balanceOf[to] += amount;
    }

    function transferOwnership(address newOwner) external onlyOwner {
        require(newOwner != address(0), "zero owner");
        owner = newOwner;
    }
}
