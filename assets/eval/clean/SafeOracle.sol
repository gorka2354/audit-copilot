// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

interface IPriceFeed {
    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80);
}

/// Оракул с проверкой свежести и валидности — не спотовая цена AMM.
/// Заведомо корректный контракт — любое срабатывание детектора здесь = false positive.
contract SafeOracle {
    IPriceFeed public immutable feed;
    uint256 public constant MAX_STALENESS = 3600;

    constructor(IPriceFeed feed_) {
        feed = feed_;
    }

    function safePrice() external view returns (uint256) {
        (, int256 answer, , uint256 updatedAt, ) = feed.latestRoundData();
        require(answer > 0, "bad price");
        require(block.timestamp - updatedAt <= MAX_STALENESS, "stale price");
        return uint256(answer);
    }
}
