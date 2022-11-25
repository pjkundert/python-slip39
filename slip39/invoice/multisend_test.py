
import json
import os
import pytest

import rlp
import solcx

from .multisend		import (
    make_trustless_multisend, build_recursive_multisend, simulate_multisends,
)

# Compiled with Solidity v0.3.5-2016-07-21-6610add with optimization enabled.
# 
# The old MultiSend contract used by https://github.com/Arachnid/extrabalance was displayed with
# incorrectly compiled abi (probably from a prior version).  I recompiled this source online at
# https://ethfiddle.com/ using solidity v0.3.5, and got roughly the same results when decompiled at
# https://ethervm.io/decompile.  However, py-solc-x doesn't have access to pre-0.4.11, we've had to
# update the contract.
multisend_0_4_11_src		= """
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
# Upgraded to support available solidity compilers
multisend_0_5_16_src		= """
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
"""

multisend_original_abi			= [
    {
        "inputs":[
            {"name":"recipients","type":"address[]"},
            {"name":"amounts","type":"uint256[]"},
            {"name":"remainder","type":"address"}
        ],
        "type":"constructor"
    },
    {
        "anonymous":False,
        "inputs":[
            {"indexed":True,"name":"recipient","type":"address"},
            {"indexed":False,"name":"amount","type":"uint256"}
        ],
        "name":"SendFailure","type":"event"
    }
]

multisend_0_4_11_abi		= [
    {
        "inputs": [
            {
                "name": "recipients",
                "type": "address[]"
            },
            {
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "name": "remainder",
                "type": "address"
            }
        ],
        "payable": False,
        "type": "constructor"
    }
]
multisend_0_4_11_contract	= bytes.fromhex(
    "60606040526040516099380380609983398101604052805160805160a05191830192019081518351600091146032576002565b5b8351811015608d5783818151"
    "81101560025790602001906020020151600160a060020a0316600084838151811015600257906020019060200201516040518090506000604051808303818588"
    "88f150505050506001016033565b81600160a060020a0316ff"
)

multisend_0_5_16_abi		= [
    {
        "inputs": [
            {
                "internalType": "address payable[]",
                "name": "recipients",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            },
            {
                "internalType": "address payable",
                "name": "remainder",
                "type": "address"
            }
        ],
        "payable": True,
        "stateMutability": "payable",
        "type": "constructor"
    }
]
multisend_0_5_16_contract	= bytes.fromhex(
    "6080604052600080fdfea265627a7a72315820823834af322d8b2e7a0136f1462a1b2373f371f18ac1b787370136aa1f6f5f6d64736f6c63430005100032"
)

trustee_address = '0xda4a4626d3e16e094de3225a751aab7128e96526'


# https://github.com/canepat/ethereum-multi-send
# Used solidity 0.5.16 (see buidler.config.js; now hardhat.org) 
multitransferether_src		= """
pragma solidity ^0.7.6;

contract MultiTransferEther {
    constructor(address payable account, address payable[] memory recipients, uint256[] memory amounts) public payable {
        require(account != address(0), "MultiTransfer: account is the zero address");
        require(recipients.length > 0, "MultiTransfer: recipients length is zero");
        require(recipients.length == amounts.length, "MultiTransfer: size of recipients and amounts is not the same");

        for (uint256 i = 0; i < recipients.length; i++) {
            recipients[i].transfer(amounts[i]);
        }
        selfdestruct(account);
    }
}
"""
multitransferether_abi		= [
    {
        "inputs": [
            {
                "internalType": "address payable",
                "name": "account",
                "type": "address"
            },
            {
                "internalType": "address payable[]",
                "name": "recipients",
                "type": "address[]"
            },
            {
                "internalType": "uint256[]",
                "name": "amounts",
                "type": "uint256[]"
            }
        ],
        # "payable": True,  # Why not payable?
        "stateMutability": "payable",
        "type": "constructor"
    }
]
multitransferether_contract	= bytes.fromhex(
    "6080604052600080fdfea2646970667358221220dfd6b117ffff81db399d86346fda6ff874f0f6a4d30a48da6bf4a2ef8be1316464736f6c63430007060033"  # TODO: This doesn't look right...
)


@pytest.mark.skipif( True, reason="Incomplete" )
def test_multisend_smoke():
    payouts = [(k, int(v)) for k, v in json.load(open( __file__[:-3]+'-payouts.json', 'r' ))]
    rootaddr, value, transactions = build_recursive_multisend(payouts, trustee_address, 110)
    gas				= simluate_multisends( payouts, transactions )
    print( "Root address 0x%s requires %d wei funding, uses %d wei gas" % (rootaddr.encode('hex'), value, gas))
    out_path			= __file__[:-3]+'-transactions.js'
    out = open(os.path.join( out_path, 'w'))
    for tx in transactions:
        out.write('web3.eth.sendRawTransaction("0x%s");\n' % (rlp.encode(tx).encode('hex'),))
    out.close()
    print( "Transactions written out to {out_path}".format( out_path=out_path ))


def test_solc_smoke():
    solcx.install_solc( version="0.7.0" )
    contract_0_7_0 = solcx.compile_source(
        "contract Foo { function bar() public { return; } }",
	output_values=["abi", "bin-runtime"],
	solc_version="0.7.0"
    )
    assert contract_0_7_0 =={
        '<stdin>:Foo': {
            'abi': [{'inputs': [], 'name': 'bar', 'outputs': [], 'stateMutability': 'nonpayable', 'type': 'function'}],
            'bin-runtime': '6080604052348015600f57600080fd5b506004361060285760003560e01c8063febb0f7e14602d575b600080fd5b60336035565b005b56fea2646970667358221220b5ea15465e27392fad41ce2ca5472bc4c1c4bacbbabe9a89eb05f1c76cd3103264736f6c63430007000033'
        },
    }

    solcx.install_solc( version="0.5.16" )
    contract_0_5_15 = solcx.compile_source(
        "contract Foo { function bar() public { return; } }",
	output_values=["abi", "bin-runtime"],
	solc_version="0.5.16"
    )
    assert contract_0_5_15 == {
        '<stdin>:Foo': {
            'abi': [
                {'constant': False,
                 'inputs': [],
                 'name': 'bar',
                 'outputs': [],
                 'payable': False,
                 'stateMutability': 'nonpayable',
                 'type': 'function'
                 }
            ],
            'bin-runtime': '6080604052348015600f57600080fd5b506004361060285760003560e01c8063febb0f7e14602d575b600080fd5b60336035565b005b56fea265627a7a72315820a3e2ebb77b4d57e436df13f2e11eb1eb086dd4c0ac7a3e88fe75fbcf7a81445d64736f6c63430005100032',
        }
    }

    assert contract_0_7_0['<stdin>:Foo']['bin-runtime'] != contract_0_5_15['<stdin>:Foo']['bin-runtime']


def test_solc_multisend():
    solcx.install_solc( version="0.5.16" )
    contract_multisend_simple = solcx.compile_source(
        multisend_0_5_16_src,
        output_values=["abi", "bin-runtime"],
        solc_version="0.5.16"
    )
    print( json.dumps( contract_multisend_simple, indent=4 ))
    assert contract_multisend_simple == {
        '<stdin>:MultiSend': {
            'abi': 		multisend_0_5_16_abi,
            'bin-runtime':	multisend_0_5_16_contract.hex(),
        }
    }

        
def test_solc_multitransferether():
    solcx.install_solc( version="0.7.6" )
    multitransferether_compile = solcx.compile_source(
        multitransferether_src,
        output_values=["abi", "bin-runtime"],
        solc_version="0.7.6"
    )
    print( json.dumps( multitransferether_compile, indent=4 ))
    assert multitransferether_compile == {
        '<stdin>:MultiTransferEther': {
            'abi': 		multitransferether_abi,
            'bin-runtime':	multitransferether_contract.hex(),
        }
    }

        
def test_solc_multipayout():

    solc_version		= "0.8.17"

    multipayout_src		= """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

// import "github.com/OpenZeppelin/openzeppelin-contracts/blob/release-v4.5/contracts/security/ReentrancyGuard.sol";
/**
 * @dev Contract module that helps prevent reentrant calls to a function.
 *
 * Inheriting from `ReentrancyGuard` will make the {nonReentrant} modifier
 * available, which can be applied to functions to make sure there are no nested
 * (reentrant) calls to them.
 *
 * Note that because there is a single `nonReentrant` guard, functions marked as
 * `nonReentrant` may not call one another. This can be worked around by making
 * those functions `private`, and then adding `external` `nonReentrant` entry
 * points to them.
 *
 * TIP: If you would like to learn more about reentrancy and alternative ways
 * to protect against it, check out our blog post
 * https://blog.openzeppelin.com/reentrancy-after-istanbul/[Reentrancy After Istanbul].
 */
abstract contract ReentrancyGuard {
    // Booleans are more expensive than uint256 or any type that takes up a full
    // word because each write operation emits an extra SLOAD to first read the
    // slot's contents, replace the bits taken up by the boolean, and then write
    // back. This is the compiler's defense against contract upgrades and
    // pointer aliasing, and it cannot be disabled.

    // The values being non-zero value makes deployment a bit more expensive,
    // but in exchange the refund on every call to nonReentrant will be lower in
    // amount. Since refunds are capped to a percentage of the total
    // transaction's gas, it is best to keep them low in cases like this one, to
    // increase the likelihood of the full refund coming into effect.
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;

    uint256 private _status;

    constructor() {
        _status = _NOT_ENTERED;
    }

    /**
     * @dev Prevents a contract from calling itself, directly or indirectly.
     * Calling a `nonReentrant` function from another `nonReentrant`
     * function is not supported. It is possible to prevent this from happening
     * by making the `nonReentrant` function external, and making it call a
     * `private` function that does the actual work.
     */
    modifier nonReentrant() {
        // On the first call to nonReentrant, _notEntered will be true
        require(_status != _ENTERED, "ReentrancyGuard: reentrant call");

        // Any calls to nonReentrant after this point will fail
        _status = _ENTERED;

        _;

        // By storing the original value once again, a refund is triggered (see
        // https://eips.ethereum.org/EIPS/eip-2200)
        _status = _NOT_ENTERED;
    }
}    

contract MultiPayout is ReentrancyGuard {
    // Payout predefined percentages of whatever ETH is in the account to a predefined set of payees.

    // Notification of Payout success/failure; significant cost in contract size; 2452 vs. ~1600 bytes
    event Payout( uint256 amount, address to, bool sent );

    constructor() payable {
        if ( address(this).balance > 0 ) {
            payout();
        }
    }

    /*
     * Processing incoming payments:
     *
     *     Which function is called, fallback() or receive()?
     *
     *            send Ether
     *                |
     *          msg.data is empty?
     *               / \
     *             yes  no
     *             /     \
     * receive() exists?  fallback()
     *          /   \
     *         yes   no
     *         /      \
     *     receive()   fallback()
     *
     * NOTE: we *can* receive ETH without processing it here, via selfdestruct(); any
     * later call (even with a 0 value) will trigger payout.
     */
    // receive() external payable { payout(); }
    fallback() external payable {
        if ( address(this).balance == 0 ) {
            payout();
        }
    }

    /*
     * Anyone may invoke payout (indirectly, by sending ETH to the contract), which transfers the balance
     * as designated by the fixed percentage factors.  The transaction's Gas/fees are paid by the
     * caller, including the case of the initial contract creation -- no Gas/fees ever come from the
     * ETH balance of the contract.  Only if NO ETH can successfully be sent to *any* address will
     * the payout fail and revert.  Any payee who wishes to be paid should ensure that their address
     * will accept an incoming transfer of ETH.
     */
     function payout() private nonReentrant {
        uint256 gone		= move_pctx100_to( 0,     690, payable( address( 0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b ))); //  6.90% to Dominion
        gone			= move_pctx100_to( gone, 4000, payable( address( 0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B ))); // 40.00% to Perry
        gone			= move_pctx100_to( gone,    0, payable( address( 0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955 ))); // (rest) to Amarissa
    }

    // Move 'pct' of the current .balance to 'dest', returning the new total 'done'
    // For example, if we are:
    // _done    == 469000000000000000 to begin with
    // .balance == 531000000000000000 remains, and we are told to move
    // _pct_x100== 10.50% == 1050
    // NOTE: changing _pct.. from uint256 to uint16 reduces contract size by ~20 bytes; unknown gas cost savings
    function move_pctx100_to( uint256 _gone, uint256 _pct_x100, address payable _to ) private returns ( uint256 ) {
        uint256 value           = address(this).balance;
        if ( _pct_x100 > 0 ) {
            value               = ( value + _gone ) * _pct_x100 / 100;
        }
        // Any value not sent to a recipient stays in the balance and is split between subsequent recipients
        (bool sent, ) = _to.call{ value: value }( "" );
        emit Payout( value, _to, sent );
        return _gone + ( sent ? value : 0 );
    }
}
"""
    multipayout_abi			= [
        {
            "inputs": [],
            "stateMutability": "payable",
            "type": "constructor"
        },
        {
            'anonymous': False,
            'inputs': [
                {'indexed': False,
                 'internalType': 'uint256',
                 'name': 'amount',
                 'type': 'uint256'},
                {'indexed': False,
                 'internalType': 'address',
                 'name': 'to',
                 'type': 'address'},
                {'indexed': False,
                 'internalType': 'bool',
                 'name': 'sent',
                 'type': 'bool'}
            ],
            'name': 'Payout',
            'type': 'event'
        },
        {
            "stateMutability": "payable",
            "type": "fallback"
        }
    ]
    multipayout_contract		= bytes.fromhex(
        "60806040526000470361001557610014610017565b5b005b60026000540361005c576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040161005390610237565b60405180910390fd5b6002600081905550600061008860006102b2737f7458ef9a583b95dfd90c048d4b2d2f09f6da5b6100da565b90506100ab81610fa07394da50738e09e2f9ea0d4c15cf8dadfb4cfc672b6100da565b90506100cd81600073a29618aba937d2b3eeaf8abc0bc6877ace0a19556100da565b9050506001600081905550565b600080479050600084111561010f5760648486836100f89190610290565b61010291906102c4565b61010c9190610335565b90505b60008373ffffffffffffffffffffffffffffffffffffffff168260405161013590610397565b60006040518083038185875af1925050503d8060008114610172576040519150601f19603f3d011682016040523d82523d6000602084013e610177565b606091505b505090507f869016d06438b769e3d28ac8765c6daa53244a8a0b5390ce314f08a43b7bab0d8285836040516101ae93929190610455565b60405180910390a1806101c25760006101c4565b815b866101cf9190610290565b925050509392505050565b600082825260208201905092915050565b7f5265656e7472616e637947756172643a207265656e7472616e742063616c6c00600082015250565b6000610221601f836101da565b915061022c826101eb565b602082019050919050565b6000602082019050818103600083015261025081610214565b9050919050565b6000819050919050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052601160045260246000fd5b600061029b82610257565b91506102a683610257565b92508282019050808211156102be576102bd610261565b5b92915050565b60006102cf82610257565b91506102da83610257565b92508282026102e881610257565b915082820484148315176102ff576102fe610261565b5b5092915050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052601260045260246000fd5b600061034082610257565b915061034b83610257565b92508261035b5761035a610306565b5b828204905092915050565b600081905092915050565b50565b6000610381600083610366565b915061038c82610371565b600082019050919050565b60006103a282610374565b9150819050919050565b6103b581610257565b82525050565b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b6000819050919050565b60006104006103fb6103f6846103bb565b6103db565b6103bb565b9050919050565b6000610412826103e5565b9050919050565b600061042482610407565b9050919050565b61043481610419565b82525050565b60008115159050919050565b61044f8161043a565b82525050565b600060608201905061046a60008301866103ac565b610477602083018561042b565b6104846040830184610446565b94935050505056fea264697066735822122078fcfb53107492bdc7a721308a5f2bc4998d51094dd6e9e32ed36eb089988b7564736f6c63430008110033"
    )

    solcx.install_solc( version=solc_version )
    multipayout_compile = solcx.compile_source(
        multipayout_src,
        output_values=["abi", "bin-runtime"],
        solc_version=solc_version,
    )
    print( json.dumps( multipayout_compile, indent=4 ))
    print( "Contract size == {} bytes".format( len( multipayout_compile['<stdin>:MultiPayout']['bin-runtime'] )))
    assert multipayout_compile == {
        '<stdin>:MultiPayout': {
            'abi': 		multipayout_abi,
            'bin-runtime':	multipayout_contract.hex(),
        },
        '<stdin>:ReentrancyGuard': {
            "abi": [],
            "bin-runtime": ""
        }
    }


    # We have a contract compiled.  Lets instantiate it, in a test EVM
    from eth_tester	import EthereumTester
    t				= EthereumTester()
    test_accounts		= t.get_accounts()
    print( "Test EVM Accounts: {}".format( json.dumps( test_accounts, indent=4 )))

    for a in test_accounts:
        print( " {} == {}".format( a, t.get_balance( a )))

    tx_hash			= t.send_transaction({
        'from': '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf',
        'to': '0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF',
        'gas': 30000,
        'value': 1,
        'max_fee_per_gas': 1000000000,
        'max_priority_fee_per_gas': 1000000000,
        'chain_id': 131277322940537,
        'access_list': (
            {
                'address': '0xde0b295669a9fd93d5f28d9ec85e40f4cb697bae',
                'storage_keys': (
                    '0x0000000000000000000000000000000000000000000000000000000000000003',
                    '0x0000000000000000000000000000000000000000000000000000000000000007',
                )
            },
            {
                'address': '0xbb9bc244d798123fde783fcc1c72d3bb8c189413',
                'storage_keys': ()
            },
        )
    })
    print( "Send ETH transaction hash: {}".format( tx_hash ))

    tx				= t.get_transaction_by_hash( tx_hash ) 
    print( "Send ETH transaction: {}".format( json.dumps( tx, indent=4 )))

    # Now construct a Signed Transaction that executes construction of this Smart Contract
    from eth_tester.validation import DefaultValidator
    validator			= DefaultValidator()

    multipayout_construct	=        {
        "from":				test_accounts[0],
        "data":				multipayout_contract.hex(),
        "value":			0,
        "gas":				300000,
        "max_fee_per_gas":		1000000000,
        "max_priority_fee_per_gas":	1000000000,
        # "r":				1,
        # "s":				1,
        # "v":				1,
    }
    validator.validate_inbound_transaction( multipayout_construct, txn_internal_type="send" ) #, txn_internal_type="send_signed" )

    mc_hash			= t.send_transaction( multipayout_construct )
    print( "Construct MultiPayout hash: {}".format( mc_hash ))

    mc				= t.get_transaction_by_hash( mc_hash ) 
    print( "Construct MultiPayout transaction: {}".format( json.dumps( mc, indent=4 )))
