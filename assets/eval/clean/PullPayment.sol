// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// Pull-over-push: получатели забирают средства сами, кредит и вывод разделены.
/// Заведомо корректный контракт — любое срабатывание детектора здесь = false positive.
contract PullPayment {
    mapping(address => uint256) private credits;

    function _asyncTransfer(address dest, uint256 amount) internal {
        credits[dest] += amount;
    }

    function withdrawPayments(address payable payee) external {
        uint256 payment = credits[payee];
        require(payment > 0, "no credit");
        credits[payee] = 0; // обнуляем кредит ДО отправки
        (bool ok, ) = payee.call{value: payment}("");
        require(ok, "transfer failed");
    }
}
