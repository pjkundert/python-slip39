pragma solidity ^0.5.15;

contract MultiSend {
    constructor(address payable[] memory recipients, uint256[] memory amounts, address payable remainder) public payable {
        // require(recipients.length == amounts.length);

        for(uint256 i = 0; i < recipients.length; i++) {
            recipients[i].send(amounts[i]);
        }

        selfdestruct(remainder);
    }
}
