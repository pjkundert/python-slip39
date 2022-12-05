
#
# Python-slip39 -- Ethereum SLIP-39 Account Generation and Recovery
#
# Copyright (c) 2022, Dominion Research & Development Corp.
#
# Python-slip39 is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is also available under alternative (eg. Commercial) licenses, at
# your option.  See the LICENSE file at the top of the source tree.
#
# Python-slip39 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#

# from ethereum		import utils, abi, transactions
# from ethereum.tools	import tester
# from ethereum.messages	import apply_transaction

from eth_tester		import EthereumTester
from web3		import Web3


#
# Patterned after:
#
# https://github.com/canepat/ethereum-multi-send:
#     pragma solidity ^0.5.15;
#
#     contract MultiTransferEther {
#         constructor(address payable account, address payable[] memory recipients, uint256[] memory amounts) public payable {
#             require(account != address(0), "MultiTransfer: account is the zero address");
#             require(recipients.length > 0, "MultiTransfer: recipients length is zero");
#             require(recipients.length == amounts.length, "MultiTransfer: size of recipients and amounts is not the same");
#
#             for (uint256 i = 0; i < recipients.length; i++) {
#                 recipients[i].transfer(amounts[i]);
#             }
#             selfdestruct(account);
#         }
#     }
#
# https://github.com/Arachnid/extrabalance
#
#     The Contract constructor executes the Ethereum send to the list of recipients, and
# finally self-destructs the contract, sending any remaining ETH to the remainder address.
#
#     The single-use address is created when the contract and its arguments are encoded into a transaction.
# A fixed signature is supplied, and thus the contract address is deduced -- from the content of the
# contract constructor call!
#
#     The *only* thing we can do on this address is... execute this contract, once!  Any failure
# abandons the funds in the address forever.  So, checking for errors is a dead end -- any ETH are
# lost.
#
#   This is because we don't *have* the private key to sign any new transaction eg. with a new
# nonce, or more correct data!  On a failure to execute the contract constructor, all we can do is
# add more Eth to the address, and retry the exact same contract constructor invocation, in the
# hopes it succeeds.  This might be a worthwhile check, if it didn't increase the cost of the call
# much.  But, it does, as each read of a word from storage costs 200 gas.
#
#    Instead of using a generic smart contract, we will generate one directly taking no arguments,
# and compile it for each unique set of fee payees/amounts (with a unique UUID), generating a unique
# destination address.
#
# ERC20 Tokens
# ============
#
#     There is no mechanism by which a recipient address/contract can be notified of incoming ERC20
# tokens: https://ethereum.stackexchange.com/questions/55067/token-forward-contract/55427#55427
# Similarly, there is no guaranteed method by which incoming ETH can be detected either -- because
# they may be delivered by another contract's 'selfdestruct' call.
#
#     If you see SSL: CERTIFICATE_VERIFY_FAILED on mac, use the 'brew install python3' version
# of Python, or run the /Applications/Python\ 3.10/Install\ Certificates.command
#
#
# Compiled with Solidity v0.3.5-2016-07-21-6610add with optimization enabled.
"""
contract MultiSend {
    function MultiSend(address[] recipients, uint[] amounts, address remainder) {
        if(recipients.length != amounts.length)
            throw;

        for(uint i = 0; i < recipients.length; i++) {
            recipients[i].send(amounts[i]);
        }

        selfdestruct(remainder);
    }
}
"""


def make_trustless_multisend( payouts, remainder, gasprice=20 * 10**9 ):
    """
    Creates a transaction that trustlessly sends money to multiple recipients, and any
    left over (unsendable) funds to the address specified in remainder.

    Arguments:
      payouts: A list of (address, value tuples)
      remainder: An address in hex form to send any unsendable balance to
      gasprice: The gas price, in wei
    Returns: A transaction object that accomplishes the multisend.
    """
    # ct = abi.ContractTranslator(multisend_abi)
    w3				= Web3()
    ct				= w3.eth.contract(
        multisend_abi
    )
    addresses = [utils.normalize_address(addr) for addr, value in payouts]
    values = [value for addr, value in payouts]
    cdata = ct.encode_constructor_arguments([addresses, values, utils.normalize_address(remainder)])
    tx = transactions.Transaction(
        0,
        gasprice,
        50000 + len(addresses) * 35000,
        '',
        sum(values),
        multisend_contract + cdata)
    tx.v = 27
    tx.r = 0x0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0
    tx.s = 0x0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0DA0
    while True:
        try:
            tx.sender
            return tx
        except Exception:
            # Failed to generate public key
            tx.r += 1


def simulate_multisends(payouts, transactions):
    t				= EthereumTester()
    t.send_transaction()

    # s = tester.state()
    # roottx = transactions[0]
    # s.state.set_balance(roottx.sender, roottx.value + roottx.startgas * roottx.gasprice)
    # gas_used = 0
    # for i, tx in enumerate(transactions):
    #     s.state.get_balance(roottx.sender)
    #     apply_transaction(s.state, tx)
    #     print( "Applying transaction number %d consumed %d gas out of %d" % (i, s.state.gas_used - gas_used, tx.startgas))
    #     gas_used = s.state.gas_used

    # for addr, value in payouts:
    #     balance = s.state.get_balance(utils.normalize_address(addr))
    #     assert balance == value, (addr, balance, value)
    # return s.state.gas_used


def build_recursive_multisend(payouts, remainder, batchsize):
    """Builds a recursive set of multisend transactions.

    Arguments:
      payouts: A map from address to value to send.
      remainder: An address to send any unsent funds back to.
      batchsize: Maximum payouts per transaction.
    Returns:
      (rootaddr, value, transactions)
    """
    transactions = []

    for i in range(0, len(payouts), batchsize):
        txpayouts = payouts[i:i + batchsize]
        tx = make_trustless_multisend(txpayouts, remainder)
        transactions.append(tx)

    if len(transactions) == 1:
        tx = transactions[0]
        return (tx.sender, tx.value + tx.startgas * tx.gasprice, transactions)
    else:
        subpayouts = [(tx.sender, tx.value + tx.startgas * tx.gasprice) for tx in transactions]
        rootaddr, value, subtx = build_recursive_multisend(subpayouts, remainder, batchsize)
        return (rootaddr, value, subtx + transactions)
