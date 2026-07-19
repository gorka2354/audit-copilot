// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title VulnerableVault
/// @notice Умышленно уязвимый контракт для демонстрации аудита. НЕ для продакшена.
///         Собран так, чтобы статические детекторы нашли несколько разных классов
///         уязвимостей и агент промаршрутизировал каждый в свой раздел базы знаний.
interface IPair {
    function getReserves() external view returns (uint112 reserve0, uint112 reserve1, uint32 ts);
}

contract VulnerableVault {
    mapping(address => uint256) public balances;
    address public owner;
    IPair public pair;

    constructor(IPair _pair) {
        owner = msg.sender;
        pair = _pair;
    }

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    /// @dev Reentrancy: внешний вызов выполняется ДО обновления состояния — нарушение
    ///      checks-effects-interactions, баланс списывается уже после отправки эфира.
    function withdraw(uint256 amount) external {
        require(balances[msg.sender] >= amount, "insufficient");
        (bool ok, ) = msg.sender.call{value: amount}("");
        require(ok, "transfer failed");
        balances[msg.sender] -= amount;
    }

    /// @dev Missing access control: сменить владельца может кто угодно — нет onlyOwner.
    function setOwner(address newOwner) external {
        owner = newOwner;
    }

    /// @dev Spot-price oracle: цена берётся из мгновенных резервов пула и потому
    ///      манипулируема флеш-лоаном в пределах одной транзакции.
    function price() public view returns (uint256) {
        (uint112 reserve0, uint112 reserve1, ) = pair.getReserves();
        return uint256(reserve1) / uint256(reserve0);
    }
}
