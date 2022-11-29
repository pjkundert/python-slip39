
import json
import os
import random

import pytest
from string		import Template

import requests
import rlp
import solcx

from web3		import Web3
from web3.contract	import normalize_address_no_ens

from ..api		import (
    account, accounts,
)

from .multisend		import (
    make_trustless_multisend, build_recursive_multisend, simulate_multisends,
)

from .ethereum		import ETH_USD, GWEI_GAS, GWEI_ETH


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


multipayout_template		= Template( """
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

//import "github.com/OpenZeppelin/openzeppelin-contracts/blob/release-v4.5/contracts/security/ReentrancyGuard.sol";
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
    ${PAYOUT}
}
""" )


def multipayout_generate( addr_pct, scale=100 ):
    """Produce payout function w/ fixed percentages to predefined addresses.  Precision """
    payout		= "function payout() private nonReentrant {\n"
    pct_tot		= 0
    for i,(addr,pct) in enumerate( sorted( addr_pct.items(), key=lambda a_p: a_p[1] )):
        if pct < 1/scale:
            continue
        payout	       += f"    {'gone' if i else 'uint256 gone':<16}"
        payout	       += f"= move_pctx{scale}_to( {'gone,' if i else '0,':<5}"
        pct_tot	       += pct
        if ( scale - 1/scale ) <= pct_tot <= ( scale + 1/scale ):
            pct		= 0
        payout	       += f" {int(pct * scale):>{2+len(str(scale))}},"
        payout	       += f" payable( address( {normalize_address_no_ens( addr )} )));\n"
    payout	       += "}\n"
    assert ( scale - 1/scale ) <= pct_tot <= ( scale + 1/scale ), \
        f"Total payout percentages didn't sum to 100%, {pct_tot:9.4f}%"

    payout	       += Template( """
function move_pctx${SCALE}_to( uint256 _gone, uint256 _pct_x${SCALE}, address payable _to ) private returns ( uint256 ) {
    uint256 value           = address(this).balance;
    if ( _pct_x${SCALE} > 0 ) {
        value               = ( value + _gone ) * _pct_x${SCALE} / ${SCALE};
    }
    // Any value not sent to a recipient stays in the balance and is split between subsequent recipients
    (bool sent, ) = _to.call{ value: value }( "" );
    emit Payout( value, _to, sent );
    return _gone + ( sent ? value : 0 );
}
""" ).substitute( SCALE=str( scale ))
    return payout


def multipayout_solidity( *args, **kwds ):
    payout		= multipayout_generate( *args, **kwds )
    return multipayout_template.substitute( PAYOUT=payout )


multipayout_defaults	=  {
    '0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b':  6.90,
    '0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B': 40.00,
    '0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955': 53.10,
}

def test_multipayout_generate():
    payout		= multipayout_generate( multipayout_defaults )
    print( payout )
    assert payout == """\
function payout() private nonReentrant {
    uint256 gone    = move_pctx100_to( 0,      690, payable( address( 0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b )));
    gone            = move_pctx100_to( gone,  4000, payable( address( 0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B )));
    gone            = move_pctx100_to( gone,     0, payable( address( 0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955 )));
}

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
"""


def test_solc_multipayout_eth_tester():
    """Use eth_tester directly to create a contract.  Doesn't allow interacting with the Goerli
    test-chain; only local test instance.

    """
    solc_version		= "0.8.17"

    multipayout_abi		= [
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
    multipayout_bytecode	= bytes.fromhex(
        "60806040526000470361001557610014610017565b5b005b60026000540361005c576040517f08c379a000000000000000000000000000000000000000000000000000000000815260040161005390610237565b60405180910390fd5b6002600081905550600061008860006102b2737f7458ef9a583b95dfd90c048d4b2d2f09f6da5b6100da565b90506100ab81610fa07394da50738e09e2f9ea0d4c15cf8dadfb4cfc672b6100da565b90506100cd81600073a29618aba937d2b3eeaf8abc0bc6877ace0a19556100da565b9050506001600081905550565b600080479050600084111561010f5760648486836100f89190610290565b61010291906102c4565b61010c9190610335565b90505b60008373ffffffffffffffffffffffffffffffffffffffff168260405161013590610397565b60006040518083038185875af1925050503d8060008114610172576040519150601f19603f3d011682016040523d82523d6000602084013e610177565b606091505b505090507f869016d06438b769e3d28ac8765c6daa53244a8a0b5390ce314f08a43b7bab0d8285836040516101ae93929190610455565b60405180910390a1806101c25760006101c4565b815b866101cf9190610290565b925050509392505050565b600082825260208201905092915050565b7f5265656e7472616e637947756172643a207265656e7472616e742063616c6c00600082015250565b6000610221601f836101da565b915061022c826101eb565b602082019050919050565b6000602082019050818103600083015261025081610214565b9050919050565b6000819050919050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052601160045260246000fd5b600061029b82610257565b91506102a683610257565b92508282019050808211156102be576102bd610261565b5b92915050565b60006102cf82610257565b91506102da83610257565b92508282026102e881610257565b915082820484148315176102ff576102fe610261565b5b5092915050565b7f4e487b7100000000000000000000000000000000000000000000000000000000600052601260045260246000fd5b600061034082610257565b915061034b83610257565b92508261035b5761035a610306565b5b828204905092915050565b600081905092915050565b50565b6000610381600083610366565b915061038c82610371565b600082019050919050565b60006103a282610374565b9150819050919050565b6103b581610257565b82525050565b600073ffffffffffffffffffffffffffffffffffffffff82169050919050565b6000819050919050565b60006104006103fb6103f6846103bb565b6103db565b6103bb565b9050919050565b6000610412826103e5565b9050919050565b600061042482610407565b9050919050565b61043481610419565b82525050565b60008115159050919050565b61044f8161043a565b82525050565b600060608201905061046a60008301866103ac565b610477602083018561042b565b6104846040830184610446565b94935050505056fea264697066735822122078fcfb53107492bdc7a721308a5f2bc4998d51094dd6e9e32ed36eb089988b7564736f6c63430008110033"
    )

    solcx.install_solc( version=solc_version )
    multipayout_compile		= solcx.compile_source(
        multipayout_solidity( multipayout_defaults ),
        output_values=["abi", "bin-runtime"],
        solc_version=solc_version,
    )
    print( json.dumps( multipayout_compile, indent=4 ))
    print( "Contract size == {} bytes".format( len( multipayout_compile['<stdin>:MultiPayout']['bin-runtime'] )))
    assert multipayout_compile['<stdin>:MultiPayout']['abi'] == multipayout_abi



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
        "data":				multipayout_compile['<stdin>:MultiPayout']['bin-runtime'],
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


georli_root_xprvkey			= account( 'ff'*32, crypto="ETH", path="m/44'/1'/0'" ).xprvkey

@pytest.mark.parametrize( "provider, src, src_prvkey, destination", [
    (
        Web3.EthereumTesterProvider(),
        '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf', None,
        (
            '0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF',
            '0x6813Eb9362372EEF6200f3b1dbC3f819671cBA69',
            '0x1efF47bc3a10a45D4B230B5d10E37751FE6AA718',
            '0xe1AB8145F7E55DC933d51a18c793F901A3A0b276',
            '0xE57bFE9F44b819898F47BF37E5AF72a0783e1141',
            '0xd41c057fd1c78805AAC12B0A94a405c0461A6FBb',
            '0xF1F6619B38A98d6De0800F1DefC0a6399eB6d30C',
            '0xF7Edc8FA1eCc32967F827C9043FcAe6ba73afA5c',
            '0x4CCeBa2d7D2B4fdcE4304d3e09a1fea9fbEb1528',
        )
    ),
    (
        Web3.WebsocketProvider( f"wss://eth-goerli.g.alchemy.com/v2/{os.getenv( 'ALCHEMY_API_TOKEN' )}" ),
        account( georli_root_xprvkey, crypto='ETH', path="m/0/0" ).address, account( georli_root_xprvkey, crypto='ETH', path="m/0/0" ).prvkey,
        tuple(
            a.address
            for a in accounts( georli_root_xprvkey, crypto="ETH", paths="m/0/1-3" )
        )
    ),
    (
        Web3.HTTPProvider( f"https://eth-goerli.g.alchemy.com/v2/{os.getenv( 'ALCHEMY_API_TOKEN' )}" ),
        account( georli_root_xprvkey, crypto='ETH', path="m/0/0" ).address, account( georli_root_xprvkey, crypto='ETH', path="m/0/0" ).prvkey,
        tuple(
            a.address
            for a in accounts( georli_root_xprvkey, crypto="ETH", paths="m/0/1-3" )
        )
    ),
])
def test_solc_multipayout_web3_tester( provider, src, src_prvkey, destination ):
    """Use web3 tester

    """
    print( f"Web3( {provider!r} ): Source ETH account: {src} (private key: {src_prvkey}; destination: {', '.join( destination )}" )

    solc_version		= "0.8.17"
    solcx.install_solc( version=solc_version )

    # Fire up Web3, and get the list of accounts we can operate on
    w3				= Web3( provider )

    latest			= w3.eth.get_block('latest')
    print( f"Web3 Latest block: {json.dumps( latest, indent=4, default=str )}" )

    print( "Web3 Tester Accounts, start of test:" )
    for a in ( src, ) + tuple( destination ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

    w3.eth.default_account	= src

    # Generate a contract targeting these destination accounts, with random percentages.
    payout_pcts			= {
        addr: random.random() * 100
        for addr in destination
    }
    unitize			= 100 / sum( payout_pcts.values() )
    payout_pcts			= {
        addr: pct * unitize
        for addr,pct in payout_pcts.items()
    }

    payout_sol			= multipayout_solidity( payout_pcts )
    print( payout_sol )
    compiled_sol		= solcx.compile_source(
        payout_sol,
        output_values	= ['abi', 'bin'],
        solc_version	= solc_version,
    )
    bytecode			= compiled_sol['<stdin>:MultiPayout']['bin']
    abi				= compiled_sol['<stdin>:MultiPayout']['abi']

    MultiPayout			= w3.eth.contract( abi=abi, bytecode=bytecode )

    if src_prvkey:
        # This is a standard contract instantiation, signed by a known account (for which we have a
        # private key) containing ETH to pay for the Gas required.  A simple example (a bit dated)
        # is at https://github.com/petervw-qa/Web3_PyStorage_Application/blob/main/deploy.py
        mc_cons_tx		= MultiPayout.constructor().build_transaction()
        print( "Web3 Tester Construct MultiPayout base transaction: {}".format( mc_cons_tx ))
        mc_cons_tx.update({ 'nonce': w3.eth.get_transaction_count( src ) })
        mc_cons_tx.update({ 'gas': 500000 })  # TODO: estimate?  Used 378774 in EtherTesterProvider...
        print( "Web3 Tester Construct MultiPayout base transaction w/nonce: {}".format( mc_cons_tx ))
        mc_cons_tx_signed	= w3.eth.account.sign_transaction( mc_cons_tx, private_key = src_prvkey )
        print( "Web3 Tester Construct MultiPayout sig. transaction: {}".format( mc_cons_tx_signed ))
        mc_cons_hash		= w3.eth.send_raw_transaction( mc_cons_tx_signed.rawTransaction )
    else:
        mc_cons_hash		= MultiPayout.constructor().transact()
    print( "Web3 Tester Construct MultiPayout hash: {}".format( mc_cons_hash ))
    mc_cons			= w3.eth.get_transaction( mc_cons_hash ) 
    print( "Web3 Tester Construct MultiPayout transaction: {}".format( json.dumps( mc_cons, indent=4, default=str )))

    mc_cons_receipt		= w3.eth.wait_for_transaction_receipt( mc_cons_hash )
    print( "Web3 Tester Construct MultiPayout receipt: {}".format( json.dumps( mc_cons_receipt, indent=4, default=str )))

    print( "Web3 Tester Construct MultiPayout Gas Used: {} == {}gwei == USD${:7.2f}".format(
        mc_cons_receipt.gasUsed,
        mc_cons_receipt.gasUsed * GWEI_GAS,
        mc_cons_receipt.gasUsed * GWEI_GAS * ETH_USD / GWEI_ETH,
    ))

    print( "Web3 Tester Accounts; post-contract creation:" )
    for a in ( src, ) + tuple( destination ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

    # We can work with the contract, but it doesn't have a direct external API -- just a fallback
    # for receiving ETH.
    multipayout			= w3.eth.contract(
        address	= mc_cons_receipt.contractAddress,
        abi	= abi,
    )

    # whatever			= w3.eth.account.create( 'Whatever' )
    # print( "Web3 Tester Whatever account created: {}".format( whatever._address ))

    # So, just send some ETH from the default account
    if src_prvkey:
        mc_send_tx		= {
            'to':	mc_cons_receipt.contractAddress,
            'from':	src,
            'nonce':	w3.eth.get_transaction_count( src ),
            'gas_price':w3.eth.gas_price,
            'gas':	100000,
            'value':	w3.to_wei( .1, 'ether' )
        }
        mc_send_tx_signed	= w3.eth.account.sign_transaction( mc_send_tx, private_key = src_prvkey )
        mc_send_hash		= w3.eth.send_raw_transaction( mc_send_tx_signed.rawTransaction )
    else:
        mc_send_hash		= w3.eth.send_transaction({
            'to':	mc_cons_receipt.contractAddress,
            'from':	src,
            'nonce':	w3.eth.get_transaction_count( src ),
            'gas_price':w3.eth.gas_price,
            'gas':	100000,
            'value':	w3.to_wei( .1, 'ether' ),
        })

    mc_send			= w3.eth.get_transaction( mc_send_hash )
    print( "Web3 Tester Send ETH MultiPayout transaction: {}".format( json.dumps( mc_send, indent=4, default=str )))

    mc_send_receipt		= w3.eth.wait_for_transaction_receipt( mc_send_hash )
    print( "Web3 Tester Send ETH MultiPayout receipt: {}".format( json.dumps( mc_send_receipt, indent=4, default=str )))

    print( "Web3 Tester Send ETH MultiPayout Gas Used: {} == {}gwei == USD${:7.2f}".format(
        mc_send_receipt.gasUsed,
        mc_send_receipt.gasUsed * GWEI_GAS,
        mc_send_receipt.gasUsed * GWEI_GAS * ETH_USD / GWEI_ETH,
    ))
    
    print( "Web3 Tester Accounts; post-send ETH:" )
    for a in ( src, ) + tuple( destination ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

