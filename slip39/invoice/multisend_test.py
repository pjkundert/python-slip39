
import json
import os
import random

from textwrap		import indent
from fractions		import Fraction
import pytest
from string		import Template

import rlp
import solcx

from web3		import Web3, logs as web3_logs
from web3.contract	import normalize_address_no_ens
from web3.middleware	import construct_sign_and_send_raw_middleware
from eth_account	import Account

from ..util		import remainder_after, into_bytes, commas
from ..api		import (
    account, accounts,
)

from .			import contract_address
from .multisend		import (
    make_trustless_multisend, build_recursive_multisend, simulate_multisends,
)

from .ethereum		import Etherscan


#
# Optimize, and search for imports relative to this directory.
#
# Don't over-optimize, or construction code gets very big (and expensive to deploy)
#
solcx_options			= dict(
    optimize		= True,
    optimize_runs	= 100,
    base_path		= os.path.dirname( __file__ ),
)


# Compiled with Solidity v0.3.5-2016-07-21-6610add with optimization enabled.

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
    gas				= simulate_multisends( payouts, transactions )
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
    assert contract_0_7_0 == {
        '<stdin>:Foo': {
            'abi': [{'inputs': [], 'name': 'bar', 'outputs': [], 'stateMutability': 'nonpayable', 'type': 'function'}],
            'bin-runtime': '6080604052348015600f57600080fd5b506004361060285760003560e01c8063febb0f7e14602d575b600080fd5b60336035565b005b56fea2646970667358221220b5ea15465e27392fad41ce2ca5472bc4c1c4bacbbabe9a89eb05f1c76cd3103264736f6c63430007000033'  # noqa: E501
        },
    }

    solcx.install_solc( version="0.5.16" )
    contract_0_5_15 = solcx.compile_source(
        "contract Foo { function bar() public { return; } }",
        output_values=["abi", "bin-runtime"],
        solc_version="0.5.16",
        **solcx_options
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
            'bin-runtime': '6080604052348015600f57600080fd5b506004361060285760003560e01c8063febb0f7e14602d575b600080fd5b60336035565b005b56fea265627a7a72315820a3e2ebb77b4d57e436df13f2e11eb1eb086dd4c0ac7a3e88fe75fbcf7a81445d64736f6c63430005100032',  # noqa: E501
        }
    }

    assert contract_0_7_0['<stdin>:Foo']['bin-runtime'] != contract_0_5_15['<stdin>:Foo']['bin-runtime']


def test_solc_multisend():
    solcx.install_solc( version="0.5.16" )
    contract_multisend_simple = solcx.compile_source(
        multisend_0_5_16_src,
        output_values=["abi", "bin-runtime"],
        solc_version="0.5.16",
        **solcx_options
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


multipayout_template		= Template( r"""
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import "openzeppelin-contracts/contracts/security/ReentrancyGuard.sol";

contract MultiPayout is ReentrancyGuard {
    // Payout predefined percentages of whatever ETH is in the account to a predefined set of payees.

    // Notification of Payout success/failure; significant cost in contract size; 2452 vs. ~1600 bytes
    event Payout( uint256 value, address to, bool sent );

    /*
     * Nothing to do in a constructor, as there is no static data
     */
    constructor() payable {
    }

    /*
     * Processing incoming payments:
     *
     *     Which function is called, fallback() or receive()?
     *
     *             send Ether
     *                 |
     *          msg.data is empty?
     *                / \
     *             yes   no
     *             /       \
     * receive() exists?  fallback()
     *          /   \
     *       yes     no
     *       /         \
     *    receive()   fallback()
     *
     * NOTE: we *can* receive ETH without processing it here, via selfdestruct(); any
     * later call (even with a 0 value) will trigger payout.
     *
     * We want incoming ETH payments to be low cost (so trigger no functionality in the receive)
     * Any other function (carrying a value of ETH or not) will trigger the fallback, which will
     * payout the ETH in the contract.
     *
     * Anyone may invoke fallback payout function (indirectly, by sending ETH to the contract), which
     * transfers the balance as designated by the fixed percentage factors.  The transaction's
     * Gas/fees are paid by the caller, including the case of the initial contract creation -- no
     * Gas/fees ever come from the ETH balance of the contract.  Only if NO ETH can successfully be
     * sent to *any* address will the payout fail and revert.  Any payee who wishes to be paid should
     * ensure that their address will accept an incoming transfer of ETH.
     */
    receive() external payable {
    }

${PAYOUT}

    fallback() external payable {
        if ( address( this ).balance > 0 ) {
            payout_internal();
        }
    }

    function payout() external payable {
        if ( address( this ).balance > 0 ) {
            payout_internal();
        }
    }
}
""" )



#
# Lets deduce the accounts to use in the Goerli Ethereum testnet.  Look for environment variables:
#
#   ..._XPRVKEY		- Use this xprv... key to generate m/../0/0 (source) and m/../0/1-3 (destination) addresses
#   ...__SEED		- Use this Seed (eg. BIP-39 Mnemonic Phrase, hex seed, ...) to generate the xprvkey
#
# If neither of those are found, use the 128-bit ffff...ffff Seed entropy.  Once you provision an
# xprvkey and derive the .../0/0 address, send some Goerli Ethereum testnet ETH to it.
#
# With no configuration, we'll end up using the 128-bit ffff...ffff Seed w/ no BIP-39 encoding as
# our root HD Wallet seed.
#
web3_testers			= []

# The Web3 tester doesn't seem to actually execute EVM contract code?

web3_testers		       += [(
    "Web3Tester",
    Web3.EthereumTesterProvider(), None,			# Provider, and chain_id (if any)
    '0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf', None,
    (
        '0x2B5AD5c4795c026514f8317c7a215E218DcCD6cF',
        '0x6813Eb9362372EEF6200f3b1dbC3f819671cBA69',
        '0x1efF47bc3a10a45D4B230B5d10E37751FE6AA718',
        # '0xe1AB8145F7E55DC933d51a18c793F901A3A0b276',
        # '0xE57bFE9F44b819898F47BF37E5AF72a0783e1141',
        # '0xd41c057fd1c78805AAC12B0A94a405c0461A6FBb',
        # '0xF1F6619B38A98d6De0800F1DefC0a6399eB6d30C',
        # '0xF7Edc8FA1eCc32967F827C9043FcAe6ba73afA5c',
        # '0x4CCeBa2d7D2B4fdcE4304d3e09a1fea9fbEb1528',
    )
),]


goerli_targets			= 3
goerli_xprvkey			= os.getenv( 'GOERLI_XPRVKEY' )
if not goerli_xprvkey:
    goerli_seed			= os.getenv( 'GOERLI_SEED' )
    if goerli_seed:
        try:
            goerli_xprvkey	= account( goerli_seed, crypto="ETH", path="m/44'/1'/0'" ).xprvkey  # why m/44'/1'?  Dunno.
        except Exception:
            pass

if goerli_xprvkey:
    # the Account.address/.key
    goerli_src			= account( goerli_xprvkey, crypto='ETH', path="m/0/0" )
    print( f"Goerli Ethereum Testnet src ETH address: {goerli_src.address}" )
    # Just addresses
    goerli_destination		= tuple(
        a.address
        for a in accounts( goerli_xprvkey, crypto="ETH", paths=f"m/0/1-{goerli_targets}" )
    )
    print( f"Goerli Ethereum Testnet dst ETH addresses: {json.dumps( goerli_destination, indent=4 )}" )

    web3_testers	       += [(
        # Web3.HTTPProvider( f"https://eth-goerli.g.alchemy.com/v2/{os.getenv( 'ALCHEMY_API_TOKEN' )}" ),
        "Goerli",
        Web3.WebsocketProvider(					# Provider and chain_id (if any)
            f"wss://eth-goerli.g.alchemy.com/v2/{os.getenv( 'ALCHEMY_API_TOKEN' )}"
        ),  None,
        goerli_src.address, goerli_src.prvkey, goerli_destination,
    ),]


# Ganache, if installed and running
ganache_targets			= 3
ganache_xprvkey			= os.getenv( 'GANACHE_XPRVKEY' )
if not ganache_xprvkey:
    ganache_seed		= os.getenv( 'GANACHE_SEED' )
    if ganache_seed:
        try:
            ganache_xprvkey	= account( ganache_seed, crypto="ETH", path="m/44'/60'/0'" ).xprvkey
        except Exception:
            pass

if ganache_xprvkey:
    # See: https://sesamedisk.com/smart-contracts-in-python-complete-guide/

    # the Account.address/.key
    ganache_src			= account( ganache_xprvkey, crypto='ETH', path="m/0/0" )
    print( f"Goerli Ethereum Testnet src ETH address: {ganache_src.address}" )
    # Just addresses
    ganache_destination		= tuple(
        a.address
        for a in accounts( ganache_xprvkey, crypto="ETH", paths=f"m/0/1-{ganache_targets}" )
    )
    print( f"Ganache Ethereum Testnet dst ETH addresses: {json.dumps( ganache_destination, indent=4 )}" )

    web3_testers		       += [(
        "Ganache",
        Web3.HTTPProvider(					# Provider and chain_id (if any)
            f"http://127.0.0.1:{os.getenv( 'GANACHE_PORT', 7545 )}",
        ), int( os.getenv( 'GANACHE_NETWORK_ID' ) or 5777 ),
        ganache_src.address, ganache_src.prvkey, ganache_destination,
    ),]


#
# MultiPayoutERC20
#
# Disburses any ETH / ERC-20 (predefined) tokens to a predetermined set of recipients, proportionally.
#
# Product Fee Distribution
# ------------------------
#
#     Guarantees that any ETH / ERC-20 tokens paid are distributed in a predetermined proportion to
# a fixed set of recipients.
#
#
# Single Use Address "Forwarder"
# ------------------------------
#
# Collect ETH/ERC-20 tokens from a single Client, either to the Product's Fee Distribution Contract
# address, or even directly to the final fee recipients.
#
#     In some situations, you may want to create payment addresses for each client, for which nobody
# has the private key -- these addresses may *only* be used to deposit ERC-20 / ETH funds, which
# then *must* be distributed according to the rules of the Contract (the code for which is known in
# advance, and the disbursement rules therefore immutable).
#
#     With a certain Contract creator source address (the owner of the product), predefined salt
# (unique per client) and Contract bytecode, the final Contract address is deterministic and
# predictable.  You can make a "one-shot" MultiPayoutERC20 Contract that flushes its ERC-20 + ETH
# contents to the specified recipient address(es) and then self-destructs.  This Smart Contract may
# be constructed, funded, executed and selfdestructed in a single invocation.  This allows
# single-use pseudo-random source addresses to be issued.
#
#     This Smart Contract is created and compiled (fixing the predefined recipients and their
# fractional allocation of all ETH and any ERC-20's).  Then, the (eventual) address of this
# deployed contract is computed:
#
#     https://forum.openzeppelin.com/t/guide-to-using-create2-sol-library-in-openzeppelin-contracts-2-5-to-deploy-a-vault-contract/2268
#
# To minimize Gas usage, attempts to follow the principles outlined in:
#
#     https://0xmacro.com/blog/solidity-gas-optimizations-cheat-sheet/
#
multipayout_ERC20_template	= Template( r"""
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import {
    IERC20,
    MultiPayoutERC20Base
} from "contracts/MultiPayoutERC20Base.sol";

import {
    MultiPayoutERC20Forwarder
} from "contracts/MultiPayoutERC20Forwarder.sol";

contract MultiPayoutERC20 is MultiPayoutERC20Base {

    //
    // Confirm/Assign that the given _data is associated with the provided _salt
    //
    // 
    //
    mapping( uint256 => bytes32 ) private _salt_data;

    error ForwarderMismatch( uint256 salt );		// The Forwarder has already been allocated w/ different _data

    event Forwarder( uint256 indexed salt );		// A new Forwarder has been allocated

    //
    // Confirm/assign _salt/_data
    // 
    // When a non-zero _data is provided, emits a Forwarder(<salt>) event to inform the MultiSendERC20
    // owner that a new, arbitrary _salt has been used.  The address should be computed, so future
    // payments to the contract may be harvested via .forwarder(<salt>).
    //
    // Only if both are bytes32(0), will a zero _data be allowed; ie. no legitimate non-zero data
    // can be overridden by a bytes32(0).  If a bytes32(0) data is supplied for a previously
    // valid non-zero _salt/_data, we'll revert with a ForwarderMismatch.  Only the owner may
    // use the 
    function _confirm_salt_data(
         uint256		_salt,
         bytes32		_data
    )
        private
    {
        bytes32 salt_data		= _salt_data[_salt];
        if ( salt_data != _data ) {
            if ( salt_data == bytes32( 0 )) {
                _salt_data[_salt]	= _data;  // must be non-zero.
                emit Forwarder( _salt );
            } else {
                revert ForwarderMismatch( _salt );
            }
        }
    }

    //
    // Confirms/assigns _salt/_data -- NOTE: This MAY make state changes
    //
    modifier confirmSaltData(
         uint256		_salt,
         bytes32		_data
    ) {
        _confirm_salt_data( _salt, _data );
        _;
    }

    event PayoutETH(   uint256 indexed value, address indexed to, bool indexed sent );
    event PayoutERC20( uint256 indexed value, address indexed to, bool indexed sent, IERC20 token );

    //
    // constructor
    //
    // This is created via standard contract creation transactions, so the address is a hash of the
    // creator's address + transaction nonce.  It will therefore be globally unique.  If we did create
    // this from another contract (using the EVM CREATE2 opcode), then for each set of identical
    // ERC-20s passed, we would need to use a unique CREATE2 salt value -- or the resultant Contract
    // address would be duplicated.  So, since we do not use CREATE2, we do not need to pass anything
    // to make the construction bytecode unique.
    //
    // Since ERC-20s are dynamic, we'll make them an array.  Since the payees / fractions are static,
    // we'll pass them textually as part of the contract code.  This is unlike the
    // openzeppelin-contracts/contracts/finance/PaymentSplitter.sol, which allows dynamic modification
    // of payees, their shares and the ERC-20 tokens supported -- and only supports "Pull" payment from
    // payees.
    //
    // We do "Push" payments (accessibly by anyone), so the payee can obtain their fees whenever they like,
    // protected by nonRentrant to ensure a hostile ERC-20 cannot re-trigger payout to inflate their share.
    //
    // Caller's address is required so that identical contracts (same payouts, ERC-20 tokens) are unique,
    // if multiple addresses instantiate them w/ the same nonce.
    //
    constructor(
       IERC20[] memory		_erc20s
    )
       payable
    {
        for ( uint256 t = 0; t < _erc20s.length; t++ ) {
            erc20s_add( _erc20s[t] );
        }
    }

    //
    // forwarder...( <salt> [,<data>] )
    //
    // Anyone can instantiate a forwarder; it can only forward the client's ETH/ERC-20 tokens to this
    // very contract.  So: fill your boots.  So long as the ERC-20 tokens supported by this Contract
    // are only settable by the Owner, it is designed to be safe for anyone to invoke.
    //
    // By convention, forwarder <salt> values allocated logically (ie. by your billing system) are
    // assumed to start at uint256( 0 ) and count up.  It is up to you to ensure you don't re-use the
    // same salt for multiple clients.  Just remember the address, and monitor it for incoming payment.
    //
    // If your client doesn't wish to use your billing system, they may allocate their own client
    // account payment address.  These are assumed to be arbitrary random uint256 <salt> values (usually,
    // derived from some unique client-specific data, like an Ed25519 public key).
    //
    // Any agent (eg. a custodial exchange wallet withdrawal) may pay the required cryptocurrency into
    // any allocated client account.
    //
    // However, at some point, either your billing system (if you're issuing the Licenses), or the
    // client itself (if it is self-provisoning the License) must invoke MultiPayoutERC20's
    // .forwarder(<salt>[,<data>]).  This uniquely and atomically associates the client's _salt with a
    // bytes32 _data -- and forwards the payment to your product's MultiPayoutERC20 contract.  An ETH
    // payment can (also) be sent to this call, simultaneously paying for and allocating the License.
    // If desired, a call to MultiPayoutERC20.forwarder_address(_salt,_data ) can also uniquely and
    // atomically allocate the address and associate _salt/_data.  Then, ETH or ERC-20s can be safely
    // transferred, and a later (more expensive) call to .forwarder(_salt) can be made (by anyone).
    //
    // There are always ways to game such a system.  However, so long as the client software's license
    // checking code isn't defeated, or it isn't run in a client environment that always returns a
    // predermined Machine ID and Ed25519 prvkey/pubkey), then the licensing checking will be atomic
    // (no 2 clients can accidentally allocate and pay into the same ...Forwarder contract address)
    // and reliable (the blockchain can be queried to determine that payment had been received to the
    // ...Forwarder contract).
    // 
    // We are checking licensing for clients: not thieves that purposely run an altered product.
    //

    //
    // Create and returns the ...Forwarder contract's address for <salt>, paying any <msg.value> thru
    // 
    // The ...Forwarder contract clears out its contract address, forwarding all ETH + ERC-20s into
    // this MultiPayoutERC20 contract.  The msg.value *could* simply be left in the MultiPayoutERC20
    // -- but, then it would *not* show as having been paid through the ...Forwarder contract address
    // as part of the transaction.  A simple Licensing check *requires* that a query of the client's
    // Forwarder contract address contains a payment.
    //
    // May be used with any <salt> whatsoever, "allocated" or not:
    //
    // Someone could collect the Forwarder(<salt>) events from all transactions on this contract,
    // compute all the possible addresses, check them for non-zero values, and execute the
    // .forwarder(<salt>) for each one containing any ETH/ERC-20 value.  For example, one of the
    // payees of the MultiPayoutERC20 contract(s) who wishes to collect their portion of the
    // contract's revenue could do it.
    //
    // Alternatively, an accounting system could determine to use a numeric sequence of <salt> values
    // eg. 0, 1, 2, 3, ..., precompute the ...Forwarder contract addresses, and never invoke
    // .forwarder(<salt>,<data>) or .forwarder_address(<salt>,<data>) to inform the MultiPayoutERC20
    // contract that such addresses are "in play" via Forwarder(<salt>) events.  Later, when some
    // address receives funds, the accounting system could detect this and invoke the
    // .forwarder(<salt>) to collect the funds -- never allocating a _salt/_data for the address (and,
    // presumably, accomplishing any client License detection some other way, or not at all).
    //
    // WARNING
    //
    // It is your client software's responsibility to use one (or both) of these approaches consistenly!
    // If you 
    function forwarder(
         uint256		_salt
    )
        public			// Callable externally and internally
        payable			// May include a non-zero ETH msg.value
        notDelegated		// Does not allow creation of MultiPayoutForwarder w/ any other address( this ) value
        returns ( address, bytes32 )
    {
        return (
            address( new MultiPayoutERC20Forwarder{
                salt:	bytes32( _salt ),		// CREATE2 opcode requires salt
                value:	msg.value			// Any msg.value is passed to ...Forwarder
            }( payable( address( this )))),		// ...Forwarder constructor requires this contract's address
            _salt_data[_salt]				// And return the _data associated with _salt (if any)
        );
    }

    // 
    // Checks (or assigns) _salt/_data, creates Forwarder for _salt and returns its address, paying any msg.value thru
    // 
    // A single call can be used to:
    // - Uniquely and atomically allocate a ...Forwarder address to a _salt, storing the client _data
    // - Pay a sum of ETH through the ...Forwarder contract, noting the payment in the blockchain
    //
    // This forms the foundation of a simple and reliable Licensing scheme.   Determine the license required
    // and the <ETH payment> required for it.  To check Licensing:
    //
    // - Query the Machine ID
    // - Create/load the client's Ed25591 signing prvkey/pubkey
    // - Sign the Machine ID using the prvkey; use 32-byte pubkey as uint256 _salt
    // - Take 256 bits of (or hash) the signature to use as bytes32 _data
    // - Invoke MultiPayoutERC20.forwarder_address( _salt ) to get (<address>, salt_data )
    //   - If salt_data == _data, and if <address> was paid the required ETH/ERC-20 value
    //     - Consider the product successfully licensed!
    //
    // If not yet licensed, query user to connect their wallet to proceed with Licensing:
    // - Use Web3 to sign and send a MultiPayoutERC20.forwarder{ value: <ETH payment>}( _salt, _data ) call
    //   - If successful,
    //     - Consider the product successfully paid and licensed!
    // 
    // Othewise, fail Licensing check.
    //
    function forwarder(
         uint256		_salt,
         bytes32		_data
    )
        external		// Callable externally only
        payable			// May include a non-zero ETH msg.value
        confirmSaltData( _salt, _data )
        returns ( address, bytes32 )
    {
        return forwarder( _salt );
    }

    //
    // Returns the Forwarder contract address for _salt, and any associated _salt_data (0 of not allocated)
    //
    // Useful for computing the pre-defined CREATE2 contract address for the specified <salt>, and detecting
    // if someone has already allocated the <salt> (associated it with a client-specific <data>).
    //
    function forwarder_address(
        uint256			_salt
    )
        public			// Callable externally and internally
        view			// No contract state changed
        returns ( address, bytes32 )
    {
        bytes memory bytecode	= type(MultiPayoutERC20Forwarder).creationCode;
        bytes memory creation	= abi.encodePacked( bytecode, abi.encode( address( this )));
        bytes32 creation_hash	= keccak256(
            abi.encodePacked( bytes1( 0xff ), address( this ), bytes32( _salt ), keccak256( creation ))
        );
        return (address( uint160( uint256( creation_hash ))), _salt_data[_salt]);
    }

    //
    // Checks (or assigns) the _salt/_data, returning the Forwarder contract address for _salt and _data
    //
    function forwarder_address(
        uint256			_salt,
        bytes32			_data
    )
        external		// Callable externally only
        confirmSaltData( _salt, _data )
        returns ( address, bytes32 )
    {
        return forwarder_address( _salt );
    }

    //
    // value_except -- Compute the value, less a certain fraction reserved.
    //
    // The _reserve is an N-bit fixed-point value with a denominator 2^N, so can only represent values
    // in the range: (0,(2^N-1)/(2^N)), or fractionally: (0,1].  Assumes that this numerator is very
    // small vs. the size of the _value.
    //
    // This assumption is almost universally true, when the value is an amount of ETH or ERC-20
    // tokens, which have large very denominators.  For example, ETH is denominated in 10^18 WEI.  So,
    // when transferring .001 ETH, the _value in this calculation will be 10^15, or
    // 1,000,000,000,000,000.  Therefore, we will normally divide by the denominator *before*
    // multiplying by the numerator -- the opposite of what we would want to do to maintain precision.
    // However, if we detect that the _value is very large (there are 1-bits within the top N bits of
    // the _value), we will do scaling in the opposite order.
    //
    // This allows us to avoid overflow (the _reserved numerator < 2^N, which *must* be the case).
    //
    function value_except(
        uint256			_value,
        uint16			_reserve		// fixed-point (0,1] w/ denominator 2^16
    )
        private
        pure			// No contract state changed or read
        returns ( uint256 )
    {
        unchecked {
            if (( _value >> ( 256 - 16 )) > 0 ) {
                // Degenerate case: 1-bits in the top 16 bits of _value.  Loses precision in low bits,
                // but maintains precision (and avoids overflow) for large values.
                return _value - (( _value >> 16 ) * _reserve );
            } else {
                // Normal case: upper N bits of _value are empty; Maintains precision in low bits (no overflow).
                return _value - (( _value * _reserve ) >> 16 );
            }
        }
    }

    //
    // transfer_ERC20_except -- transfer this ERC-20 token (if any) into 'to', reserving a proportion.
    //
    // ERC-20 .transfer call uses its msg.sender as from (ie. this contract address)
    //
    function transfer_ERC20_except(
        IERC20			_erc20,
        address payable		_to,
        uint16			_reserve		// fixed-point (0,1] w/ denominator 2^16
    )
        private
        returns (bool, uint256)  // true iff successful, and any ERC-20 token amount transferred
    {
        uint256 tok_balance;
        try _erc20.balanceOf( address( this )) returns ( uint256 balance ) {
            if ( balance > 0 ) {
                uint256 value		= value_except( balance, _reserve );
                try _erc20.transfer( _to, value ) returns (bool sent) {
                    return (sent, value );		// Success/failure transferring tok_value
                } catch {
                    return (false, value );		// Exception, trying to transfer tok_value
                }
            }
        } catch {
            return (false, 0);				// Exception, unknown ERC-20 amount
        }
        return (true, 0);				// Successful, but nothing to transfer
    }

    //
    // Transfer all but reserve fraction of ERC-20s and ETH into 'to'.
    //
    // Execute the final ETH transfer if *any* ERC-20 token(s) moved, even if the value is 0
    // ETH.  This will trigger any subsidiary MultiPayoutERC20 contract to (also) payout.
    //
    // It is possible to use a large amount of gas, if many MultiPayoutERC20 contracts are
    // chained together, and many ERC-20 tokens are involved.  If the global gas limit is
    // exceeded, remove some supported ERC-20 tokens (temporarily) and try again.
    //
    function transfer_except(
        address payable		_to,
        uint16			_reserve		// fixed-point (0,1] w/ denominator 2^16
    )
        private
    {
        bool erc20s_sent = false;
        for ( uint256 t = erc20s.length; t > 0; --t ) {
            IERC20 token		= erc20s[t-1];
            (bool tok_sent, uint256 tok_value) = transfer_ERC20_except( token, _to, _reserve );
            if ( tok_value > 0 ) {
                emit PayoutERC20( tok_value, _to, tok_sent, token );
                if ( tok_sent ) {
                    erc20s_sent = true;  // We successfully sent some ERC-20 tokens into '_to'
                }
            }
        }
        uint256 eth_balance		= address( this ).balance;
        if ( eth_balance > 0 || erc20s_sent ) {
            // Some ETH or ERC-20s sent into '_to'; trigger its receive/fallback.  If its another
            // MultiPayoutERC20, this will trigger its own payout (even if eth_value is 0).
            uint256 eth_value		= value_except( eth_balance, _reserve );
            (bool eth_sent, )  		= _to.call{ value: eth_value }( "" );
            emit PayoutETH( eth_value, _to, eth_sent );
        }
    }

    //
    // payout_internal Executes the ERC-20 / ETH transfers to the predefined accounts / fractions
    //
    function payout_internal()
        private
    {
${RECIPIENTS}
    }

    //
    // Anyone may invoke the payout API, resulting in all ETH and predefined ERC-20 tokens being
    // distributed as determined at contract creation.
    //
    function payout()
        external
        payable
        nonReentrant
    {
        payout_internal();
    }

    /*
     * Processing incoming payments:
     *
     *     Which function is called, fallback() or receive()?
     *
     *             send Ether
     *                 |
     *          msg.data is empty?
     *                / \
     *             yes   no
     *             /       \
     * receive() exists?  fallback()
     *          /   \
     *       yes     no
     *       /         \
     *    receive()   fallback()
     *
     * NOTE: we *can* receive ETH without processing it here, via selfdestruct(); any later call
     * (even with a 0 value) will trigger payout.  Since the .forward( N ) contract uses
     * selfdestruct to collect ETH, no payout will be run on a standard incoming client payment.
     *
     * This contract is designed to allow any downstream payout recipient to execute the
     * payout function, as simply as possible.  Thus, we have no receive function, and
     * specify a fallback function that executes the payout().  Thus, any incoming ETH
     * transfer to the contract (except via selfdestruct) will attempt to run payout.
     *
     * So, any wallet which can specify a high gas limit for a transfer transaction may be used.
     * Just transfer 0 ETH to the contract, and set a high gas limit (to allow for all the
     * payout proportion calculations and any ERC-20 transfers to each payout recipient).  Using
     * .send/.transfer will not work, due to the low gas limit.
     */
    fallback()
        external
        payable
        nonReentrant
    {
        payout_internal();
    }

    receive()
        external
        payable
        nonReentrant
    {
        payout_internal();
    }
}
""" )


def multipayout_ERC20_recipients( addr_frac, bits=16 ):
    """Produce recipients array elements w/ fixed fractional/proportional amounts to predefined
    addresses.  Convert proportions in the range [0,1) totaling to exactly 1.0 to a remainder
    fraction within a multiple of 2**bits, or will raise Exception.  It is not valid to specify
    a recipient with a zero proportion.

    The incoming { addr: proportion,... } dict values will be normalized, so any numeric/fractional
    values may be used (eg. arbitrary numeric "shares").

    So long as the final remainder is within +/- 1/scale of 0, its int will be zero, and
    this function will succeed.  Otherwise, it will terminate with a non-zero remainder,
    and will raise an Exception.

    The Gas cost of shifts is 3 (FASTESTSTEP), divisions is 5 (FASTSTEP), so striving to use a scale
    multiplier that is a power of 2 and known at compile-time would be best: eg. a fixed-point
    denominator that is some factor of the bit-size of the numerator.

    Since we're producing fractions in the range (0,1], the fixed-point denominator can be the 2^N
    for an N-bit value supporting the range (0,2^N-1) -- the largest possible fraction we can represent
    will be (2^N-1)/(2^N).  Eg, for a 16-bit value:

        65535/65536 =~= 0.9999847412
            1/65536 =~= 0.0000152588

    """
    addr_frac_sorted		= sorted( addr_frac.items(), key=lambda a_p: a_p[1] )
    addresses,fractions		= zip( *addr_frac_sorted )

    payout			= ""
    fractions_total		= sum( fractions )
    i				= None
    for i,(addr,frac,rem) in enumerate( zip(
            addresses,
            fractions,
            remainder_after(
                fractions,
                scale	= 2 ** bits / fractions_total,  # If Fraction, will remain a Fraction
                total	= 2 ** bits,
            )
    )):
        assert frac > 0, \
            f"Encountered a zero proportion: {frac} for recipient {addr}"
        rem_scale		= int( rem )
        assert rem_scale < 2 ** bits, \
            f"Encountered a remainder fraction: {rem_scale} numerator greater or equal to the denominator: {2**bits}"
        payout		       += f"transfer_except( payable( address( {normalize_address_no_ens( addr )} )), uint{bits}( {rem_scale:>{len(str(2**bits))}} ));  // {float(frac * 100 / fractions_total):7.3f}%\n"
    assert i is not None and rem_scale == 0, \
        f"Total payout percentages didn't accumulate to zero remainder: {rem:7.4f} =~= {rem_scale}, for {commas( fractions, final='and' )}"
    return payout


multipayout_defaults_proportion	= {
    '0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b':  6.90 / 100,
    '0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B': 40.00 / 100,
    '0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955': 53.10 / 100,
}

multipayout_defaults_percent	= {
    '0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b':  6.90,
    '0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B': 40.00,
    '0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955': 53.10,
}

multipayout_defaults_shares	= {
    '0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b':  690,
    '0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B': 4000,
    '0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955': 5310,
}

multipayout_defaults_Fraction	= {
    '0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b': Fraction(  690, 10000 ),
    '0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B': Fraction( 4000, 10000 ),
    '0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955': Fraction( 5310, 10000 ),
}


@pytest.mark.parametrize( "multipayout_defaults", [
    ( multipayout_defaults_proportion ),
    ( multipayout_defaults_percent ),
    ( multipayout_defaults_shares ),
    ( multipayout_defaults_Fraction ),
])
def test_multipayout_ERC20_recipients( multipayout_defaults ):
    payout			= multipayout_ERC20_recipients( multipayout_defaults )
    print()
    print( payout )
    assert payout == """\
transfer_except( payable( address( 0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b )), uint16( 61014 ));  //   6.900%
transfer_except( payable( address( 0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B )), uint16( 37378 ));  //  40.000%
transfer_except( payable( address( 0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955 )), uint16(     0 ));  //  53.100%
"""


@pytest.mark.parametrize( "multipayout_defaults, expected", [
    (
        # Tiny recipients that round to almost zero receive the smallest representable proportion
        {
            '0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b': 1,
            '0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B': 100000,
        },"""\
transfer_except( payable( address( 0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b )), uint16( 65535 ));  //   0.001%
transfer_except( payable( address( 0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B )), uint16(     0 ));  //  99.999%
"""
    ),
])
def test_multipayout_ERC20_recipients_corner( multipayout_defaults, expected ):
    assert multipayout_ERC20_recipients( multipayout_defaults ) == expected


def multipayout_ERC20_solidity( addr_frac, **kwds ):
    recipients			= multipayout_ERC20_recipients( addr_frac, **kwds )
    prefix			= ' ' * 8
    return multipayout_ERC20_template.substitute(
        RECIPIENTS	= indent( recipients, prefix ),
    )


@pytest.mark.parametrize( "multipayout_defaults", [
    ( multipayout_defaults_proportion ),
    ( multipayout_defaults_percent ),
    ( multipayout_defaults_shares ),
    ( multipayout_defaults_Fraction ),
])
def test_multipayout_ERC20_solidity( multipayout_defaults ):
    solidity			= multipayout_ERC20_solidity(
        addr_frac	= multipayout_defaults,
    )
    # print()
    # print( solidity )


@pytest.mark.parametrize('address, salt, contract, expected_address', [
    (
        '0x0000000000000000000000000000000000000000',
        '0x0000000000000000000000000000000000000000000000000000000000000000',
        '0x00',
        '0x4D1A2e2bB4F88F0250f26Ffff098B0b30B26BF38',
    ),
    (
        '0xdeadbeef00000000000000000000000000000000',
        '0x0000000000000000000000000000000000000000000000000000000000000000',
        '0x00',
        '0xB928f69Bb1D91Cd65274e3c79d8986362984fDA3',
    ),
    (
        '0xdeadbeef00000000000000000000000000000000',
        '0x000000000000000000000000feed000000000000000000000000000000000000',
        '0x00',
        '0xD04116cDd17beBE565EB2422F2497E06cC1C9833',
    ),
    (
        '0x0000000000000000000000000000000000000000',
        '0x0000000000000000000000000000000000000000000000000000000000000000',
        '0xdeadbeef',
        '0x70f2b2914A2a4b783FaEFb75f459A580616Fcb5e',
    ),
    (
        '0x00000000000000000000000000000000deadbeef',
        '0x00000000000000000000000000000000000000000000000000000000cafebabe',
        '0xdeadbeef',
        '0x60f3f640a8508fC6a86d45DF051962668E1e8AC7',
    ),
    (
        '0x00000000000000000000000000000000deadbeef',
        '0x00000000000000000000000000000000000000000000000000000000cafebabe',
        '0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef',
        '0x1d8bfDC5D46DC4f61D6b6115972536eBE6A8854C',
    ),
    (
        '0x0000000000000000000000000000000000000000',
        '0x0000000000000000000000000000000000000000000000000000000000000000',
        '0x',
        '0xE33C0C7F7df4809055C3ebA6c09CFe4BaF1BD9e0',
    ),
])
def test_create2(address, salt, contract, expected_address):
    """Test the CREATE2 opcode Python implementation.

    EIP-104 https://github.com/ethereum/EIPs/blob/master/EIPS/eip-1014.md

    """
    assert contract_address( address, salt=salt, contract=contract ) == expected_address

@pytest.mark.parametrize('address, nonce, expected_address', [
    (
        '0x6ac7ea33f8831ea9dcc53393aaa88b25a785dbf0',
        0,
        '0xcd234a471b72ba2f1ccf0a70fcaba648a5eecd8d',
    ),
    (
        '0x6ac7ea33f8831ea9dcc53393aaa88b25a785dbf0',
        1,
        '0x343c43a37d37dff08ae8c4a11544c718abb4fcf8',
    ),
])
def test_create2(address, nonce, expected_address):
    """Test the CREATE opcode (or transaction-based) contract creation address calculation.

    """
    assert contract_address( address, nonce=nonce ) == expected_address


HOT			= "0x6c6EE5e31d828De241282B9606C8e98Ea48526E2"
USDT			= "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDT_GOERLI		= "0xe802376580c10fE23F027e1E19Ed9D54d4C9311e"
USDC			= "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
USDC_GOERLI		= "0xde637d4C445cA2aae8F782FFAc8d2971b93A4998"

# Some test ERC-20 tokens that will mint
#     https://ethereum.stackexchange.com/questions/38743/where-can-i-find-erc20-token-faucets-for-testing
WEEN_GOERLI		= "0xaFF4481D10270F50f203E0763e2597776068CBc5"  # 18 decimals
YEEN_GOERLI		= "0xc6fDe3FD2Cc2b173aEC24cc3f267cb3Cd78a26B7"  # 8 decimals
ZEEN_GOERLI		= "0x1f9061B953bBa0E36BF50F21876132DcF276fC6e"  # 0 decimals; order of multiplication will affect precision


#
# Test the ...Forwarder -> MultiPayoutERC20 -> Recipient flow
#
# Here are the Goerli testnet results from the first successful test:
#
# The funds came from the 0x667A... source account, and were:
#
#       .01 ETH
#    820.00 WEENUS
#    757    ZEENUS
#
# and were transferred into the fwd (Forwarder contract account):
#
#    Goerli    : Web3 Tester Accounts; MultiPayoutERC20 post-send ETH/*EENUS ERC-20 to Forwarder#0:
#    - 0x667AcC3Fc27A8EbcDA66E7E01ceCA179d407ce00 == 564697006956028403 src
#      o WEENUS ERC-20 == 7,380.00
#      o ZEENUS ERC-20 == 6,813.00
#    - 0x7Fc431B8FC8250A992567E3D7Da20EE68C155109 == 100051549200000000
#    - 0xE5714055437154E812d451aF86239087E0829fA8 == 49479221300000000
#    - 0xEeC2b464c2f50706E3364f5893c659edC9E4153A == 140469229500000000
#    - 0xf57892E0022dA90c614E2074219726796e213703 == 0 payout
#    - 0xcB5dc1F473A32f18dD4B834d8979fe914e249890 == 10000000000000000 fwd
#      o WEENUS ERC-20 == 820.00
#      o ZEENUS ERC-20 == 757.00
#
# Then, the Forwarder contract was triggered, moving all ETH and (known) ERC-20s
# into the payout (MultiPayoutERC20) contract:
#
#    Goerli    : Web3 Tester Forward#0 forwarder Gas Used: 144884 == 2607912.0gwei == USD$     3.31 (Thu Dec 15 21:44:05 2022 UTC)
#    Goerli    : Web3 Tester Accounts; MultiPayoutERC20 post-instantiate Forwarder#0 again:
#    - 0x667AcC3Fc27A8EbcDA66E7E01ceCA179d407ce00 == 564696072285148775 src
#      o WEENUS ERC-20 == 7,380.00
#      o ZEENUS ERC-20 == 6,813.00
#    - 0x7Fc431B8FC8250A992567E3D7Da20EE68C155109 == 100051549200000000
#    - 0xE5714055437154E812d451aF86239087E0829fA8 == 49479221300000000
#    - 0xEeC2b464c2f50706E3364f5893c659edC9E4153A == 140469229500000000
#    - 0xf57892E0022dA90c614E2074219726796e213703 == 10000000000000000 payout
#      o WEENUS ERC-20 == 820.00
#      o ZEENUS ERC-20 == 757.00
#    - 0xcB5dc1F473A32f18dD4B834d8979fe914e249890 == 0 fwd
#
# This version used 144884 Gas; about $4.02, w/ ETH at USD$1,261.66 and Gas Base: 21 + Priority: 1
# (20 gwei/gas).  Fortunately, you can wait for a lower-cost time to harvest your payments; on
# weekends gas costs are low, so at 10 Gwei/Gas, the cost would be $2.00.  This transaction
# transported 2 ERC-20 tokens + some (test) Eth; a transaction with no ERC-20s and only ETH would be
# significantly cheaper.
#
# Finally, the payout was triggered, flushing all ETH and ERC-20s by predefined proportion into the
# 3 recipient accounts:
#
#    Goerli    : Web3 Tester payout MultiPayoutERC20 Gas Used: 270265 == 4864770.0gwei == USD$     6.17 (Thu Dec 15 21:44:05 2022 UTC)
#    Goerli    : Web3 Tester Accounts; MultiPayoutERC20 post-payout ETH:
#    - 0x667AcC3Fc27A8EbcDA66E7E01ceCA179d407ce00 == 564694320515254900 src
#      o WEENUS ERC-20 == 7,380.00
#      o ZEENUS ERC-20 == 6,813.00
#    - 0x7Fc431B8FC8250A992567E3D7Da20EE68C155109 == 109406549200000000
#      o WEENUS ERC-20 == 767.11
#      o ZEENUS ERC-20 == 708.00
#    - 0xE5714055437154E812d451aF86239087E0829fA8 == 49813782800000000
#      o WEENUS ERC-20 == 27.43
#      o ZEENUS ERC-20 == 25.00
#    - 0xEeC2b464c2f50706E3364f5893c659edC9E4153A == 140779668000000000
#      o WEENUS ERC-20 == 25.46
#      o ZEENUS ERC-20 == 24.00
#    - 0xf57892E0022dA90c614E2074219726796e213703 == 0 payout
#    - 0xcB5dc1F473A32f18dD4B834d8979fe914e249890 == 0 fwd
#    PASSED
#
# Anyone can trigger the MultiPayoutERC20.forwarder( N ) to collect a payment, and anyone can then
# trigger the MultiPayoutERC20's payout function to distribute the funds -- so, every potential
# recipient can choose to collect the funds and receive their proportion, even if the company or
# individual running the payment system fails or is otherwise incapacitated.  And, *nobody* in any
# organization can alter the collection, payout or distribution proportion of the funds: everyone
# gets paid, exactly as originally specified -- no trusted intermediaries required.
#
# All of these addresses will persist in the Goerli network, so you should be able to find
# these transactions to this day:
#
#     https://goerli.etherscan.io/address/0xcB5dc1F473A32f18dD4B834d8979fe914e249890
#
@pytest.mark.parametrize( "testnet, provider, chain_id, src, src_prvkey, destination", web3_testers )
def test_solc_multipayout_ERC20_web3_tester( testnet, provider, chain_id, src, src_prvkey, destination ):
    """Use web3 tester

    """
    print( f"{testnet:10}: Web3( {provider!r} ), w/ chain_id: {chain_id}: Source ETH account: {src} (private key: {src_prvkey}; destination: {', '.join( destination )}" )

    solc_version		= "0.8.17"
    solcx.install_solc( version=solc_version )

    # For testing we'll use the Ethereum chain's gas pricing.
    ETH				= Etherscan( "Ethereum" )

    # Fire up Web3, and get the list of accounts we can operate on
    w3				= Web3( provider )

    # Compute the gas fees we need to use for this test.  We'll use the real Ethereum chain pricing.
    # These gas pricing calculations are very complex:
    #
    #     https://docs.alchemy.com/docs/how-to-build-a-gas-fee-estimator-using-eip-1559)
    #
    # It is best to use a gas price estimator (Oracle) that predicts what the next block's likely
    # gas pricing is going to be.  The base fee is mandatory (set by the Ethereum network).  The
    # priority fee "tip" is the only thing we can adjust.
    #
    # If the fees are just too high, and the user has the option to wait (for example, when
    # executing the MultiPayoutERC20's payout function, or executing the .forward( N ) contract to
    # collect a client's payment), we need to provide that information.
    #
    # So, we need to:
    #   - estimate the gas cost to run each contract.
    #     - This will be determined by the mix of ERC-20 tokens being transferred, and the exact
    #       code each ERC-20 contract uses to execute their transfer.
    #     - It could change, if any ERC_20 uses forwarding, and changes their underlying contract
    #     - So, we'll have to test w/ all tokens resident, to get the likely maximum gas fee to
    #       run the contract, and provide a margin
    #


    # How do we specify a chain_id?
    # if chain_id is not None:
    #     w3.eth.chain_id		= chain_id

    latest			= w3.eth.get_block('latest')
    print( f"{testnet:10}: Web3 Latest block: {json.dumps( latest, indent=4, default=str )}" )

    # Ask the connected Ethereum testnet what it thinks gas prices are.  This will
    # (usually) be a Testnet, where gas prices are artificially low vs. the real Ethereum
    # network.
    max_priority_fee		= w3.eth.max_priority_fee
    base_fee			= latest['baseFeePerGas']
    est_gas_wei			= base_fee + max_priority_fee
    max_gas_wei			= base_fee * 2 + max_priority_fee  # fail transaction if gas prices go wild
    print( "{:10}: Web3 Tester Gas Price at USD${:9,.2f}/ETH: fee gwei/gas est. base (latest): {:9,.2f} priority: {:9,.2f}; cost per 100,000 gas: {} == {}gwei == USD${:9,.2f} ({}); max: USD${:9,.2f}".format(
        testnet, ETH.ETH_USD,
        base_fee / ETH.GWEI_WEI, max_priority_fee / ETH.GWEI_WEI,
        100000,
        100000 * est_gas_wei / ETH.GWEI_WEI,
        100000 * est_gas_wei * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
        100000 * max_gas_wei * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
    ))

    gas_price_testnet		= dict(
        maxFeePerGas		= max_gas_wei,		# If we want to fail if base fee + priority fee exceeds some limits
        maxPriorityFeePerGas	= max_priority_fee,
    )
    print( f"{testnet:10}: Gas Pricing EIP-1559 for max $1.50 per 21,000 Gas transaction: {json.dumps( gas_price_testnet )}" )

    # Let's say we're willing to pay up to $1.50 for a standard Ethereum transfer costing 21,000 gas
    max_usd_per_gas		= 1.50 / 21000

    print( f"{testnet:10}: Web3 Tester Accounts, start of test:" )
    for a in ( src, ) + tuple( destination ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

    # If we are providing an account with a private key to sign transactions with, we have to
    # provide a middleware shim to provision it for transaction signing.  From:
    # https://web3py.readthedocs.io/en/latest/web3.eth.account.html
    w3.eth.default_account	= src
    if src_prvkey:
        account			= Account.from_key( '0x' + src_prvkey )
        w3.middleware_onion.add(
            construct_sign_and_send_raw_middleware( account ))
        assert account.address == src, \
            f"private key 0x{src_prvkey} isn't related to address {src}"
        src_prvkey		= None

    # Generate a contract targeting these destination accounts, with random Fractional percentages.
    # We'll make sure at the end that each target account got that fraction of the values put into
    # the fwd account.  We'll select from 1 to N of the N destination accounts, and no account can
    # receive 0%.
    addr_frac			= {
        addr: 1+random.choice(range(1000))
        for addr in destination[random.choice(range(len(destination))):]
    }

    # Must be actual ERC-20 contracts; if these fail to have a .balanceOf or .transfer API, this
    # contract will fail.  So, if an ERC-20 token contract is self-destructed, the
    # MultiTransferERC20 would begin to fail, unless we caught and ignored ERC-20 API exceptions.
    tokens			= [ USDT_GOERLI, USDC_GOERLI, WEEN_GOERLI, ZEEN_GOERLI ]
    payout_sol			= multipayout_ERC20_solidity( addr_frac=addr_frac, bits=16 )
    print( payout_sol )
    compiled_sol		= solcx.compile_source(
        payout_sol,
        output_values	= ['abi', 'bin'],
        solc_version	= solc_version,
        **solcx_options
    )
    print( f"{testnet:10}: {json.dumps( compiled_sol, indent=4, default=str )}" )

    bytecode			= compiled_sol['<stdin>:MultiPayoutERC20']['bin']
    abi				= compiled_sol['<stdin>:MultiPayoutERC20']['abi']

    MultiPayoutERC20		= w3.eth.contract( abi=abi, bytecode=bytecode )

    gas				= 2000000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_cons_hash		= MultiPayoutERC20.constructor( tokens ).transact({
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 hash: {mc_cons_hash.hex()}" )
    mc_cons			= w3.eth.get_transaction( mc_cons_hash )
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 transaction: {json.dumps( mc_cons, indent=4, default=str )}" )

    mc_cons_receipt		= w3.eth.wait_for_transaction_receipt( mc_cons_hash )
    mc_cons_addr		= mc_cons_receipt.contractAddress

    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 receipt: {json.dumps( mc_cons_receipt, indent=4, default=str )}" )
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 Contract: {len( bytecode)} bytes, at Address: {mc_cons_addr}" )
    print( "{:10}: Web3 Tester Construct MultiPayoutERC20 Gas Used: {} == {}gwei == USD${:9,.2f} ({}): ${:7.6f}/byte".format(
        testnet,
        mc_cons_receipt.gasUsed,
        mc_cons_receipt.gasUsed * ETH.GAS_GWEI,
        mc_cons_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
        mc_cons_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI / len( bytecode ),
    ))

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-contract creation:" )
    for a in ( src, ) + tuple( destination ) + ( mc_cons_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ('payout' if a == mc_cons_addr else '')}" )

    multipayout_ERC20		= w3.eth.contract(
        address	= mc_cons_addr,
        abi	= abi,
    )
    # Look up the contract interface we've imported as IERC20Metadata, and use its ABI for accessing *EENUS ERC-20 tokens
    # We're aliasing it to IERC20 in the contract code, but its ABI is under its original name.
    IERC20_key,			= ( k for k in compiled_sol.keys() if k.endswith( ":IERC20Metadata" ))
    WEEN_IERC20			= w3.eth.contract(
        address	= WEEN_GOERLI,
        abi	= compiled_sol[IERC20_key]['abi'],
    )
    ZEEN_IERC20			= w3.eth.contract(
        address	= ZEEN_GOERLI,
        abi	= compiled_sol[IERC20_key]['abi'],
    )

    # Now that we have our MultiPayoutERC20 contract addresss, we can predict the Contract addresses
    # of our unique MultiPayoutERC20Forwarder contracts.  This is the contract that forwards ERC-20s
    # / ETH to a fixed destination address -- in this case, the MultiPayoutERC20 contract, and
    # nowhere else.  We can generate a deterministic sequence of new ForwarderERC20 contracts using
    # the CREATE2 opcode, and we can predict what each of their addresses will be because we can
    # know (we can compute) the creation bytecode that will be used, the sequence of salts that we
    # will use, and (now) we have the source Contract address that will be creating each one.  Lets
    # confirm.
    #
    # 1) Lets get the same ForwarderERC20 code our MultiPayoutERC20 contract is using, and prepare
    #    to generate calls to it:
    fwd_bytecode		= compiled_sol['contracts/MultiPayoutERC20Forwarder.sol:MultiPayoutERC20Forwarder']['bin']
    fwd_abi			= compiled_sol['contracts/MultiPayoutERC20Forwarder.sol:MultiPayoutERC20Forwarder']['abi']
    MultiPayoutERC20Forwarder	= w3.eth.contract( abi=fwd_abi, bytecode=fwd_bytecode )

    # 2) Get the contract creation bytecode, including constructor arguments:
    #    (see: https://github.com/safe-global/safe-eth-py/blob/master/gnosis/safe/safe_create2_tx.py)
    fwd_creation_code		= MultiPayoutERC20Forwarder.constructor( mc_cons_addr ).data_in_transaction;

    # 3) Compute the 0th MultiPayoutERC20Forwarder Contract address, targeting this MultiPayoutERC20 Contract.
    salt_0			= w3.codec.encode( [ 'uint256' ], [ 0 ] )
    mc_fwd0_addr_precomputed	= contract_address(
        address		= mc_cons_addr,
        salt		= salt_0,
        creation	= fwd_creation_code,
    )
    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address: {mc_fwd0_addr_precomputed} (precomputed)" )

    gas				= 250000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_fwd0_aclc_hash		= MultiPayoutERC20.functions.forwarder_address( 0 ).transact({
        'to':		mc_cons_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    mc_fwd0_aclc_tx		= w3.eth.get_transaction( mc_fwd0_aclc_hash )
    mc_fwd0_aclc_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_aclc_hash )
    print( "{:10}: Web3 Tester Forward#0 forwarder_address Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_aclc_receipt.gasUsed,
        mc_fwd0_aclc_receipt.gasUsed * ETH.GAS_GWEI,
        mc_fwd0_aclc_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))

    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address Receipt: {json.dumps( mc_fwd0_aclc_receipt, indent=4, default=str )} (calculated)" )
    gas				= 250000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    # The result is the (address, bytes32) associated with this salt
    mc_fwd0_aclc_result,mc_fwd0_aclc_data = multipayout_ERC20.functions.forwarder_address( 0 ).call({
        'to':		mc_cons_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address: {mc_fwd0_aclc_result} (calculated), and associated data: {mc_fwd0_aclc_data!r}" )

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 pre-instantiate Forwarder#0:" )
    for a in ( src, ) + tuple( destination ) + ( mc_cons_addr, ) + ( mc_fwd0_addr_precomputed, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ('fwd' if a == mc_fwd0_addr_precomputed else ('payout' if a == mc_cons_addr else ''))}" )

    # This is where Web3Tester goes off the rails; doesn't appear to actually execute EVM contract code?
    if testnet == "Web3Tester":
        return

    # Get the decimals for each ERC-20 token, so we can correctly represent the tokens held
    gas				= 25000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    WEEN_DEN			= 10 ** WEEN_IERC20.functions.decimals().call({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    ZEEN_DEN			= 10 ** ZEEN_IERC20.functions.decimals().call({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )

    # Lets actually deploy the 0th MultiPayoutERC20Forwarder and confirm that it is created at the
    # expected address.
    gas				= 500000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_fwd0_addr,mc_fwd0_data	= multipayout_ERC20.functions.forwarder( 0 ).call({
        'to':		mc_cons_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address: {mc_fwd0_addr} (instantiated), and associated data: {mc_fwd0_data!r}" )

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-instantiate Forwarder#0:" )
    for a in ( src, ) + tuple( destination ) + ( mc_cons_addr, ) + ( mc_fwd0_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ('fwd' if a == mc_fwd0_addr else ('payout' if a == mc_cons_addr else ''))}" )

    assert mc_fwd0_addr == mc_fwd0_aclc_result == mc_fwd0_addr_precomputed

    # Send a 0-value transaction to *EENUS and get 1,000 tokens back.  These are ERC-20 minting transactions, so will require more gas.
    gas				= 100000
    spend			= gas * max_usd_per_gas
    gas_pric			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_ween_hash		= w3.eth.send_transaction({
        'to':		WEEN_GOERLI,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    mc_ween_receipt		= w3.eth.wait_for_transaction_receipt( mc_ween_hash )
    print( f"{testnet:10}: Web3 Tester Send ETH to WEENUS receipt: {json.dumps( mc_ween_receipt, indent=4, default=str ) }" )
    print( "{:10}: Web3 Tester Send ETH to WEENUS Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_ween_receipt.gasUsed,
        mc_ween_receipt.gasUsed * ETH.GAS_GWEI,
        mc_ween_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))

    mc_zeen_hash		= w3.eth.send_transaction({
        'to':		ZEEN_GOERLI,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    mc_zeen_receipt		= w3.eth.wait_for_transaction_receipt( mc_zeen_hash )
    print( f"{testnet:10}: Web3 Tester Send ETH to ZEENUS receipt: {json.dumps( mc_zeen_receipt, indent=4, default=str ) }" )
    print( "{:10}: Web3 Tester Send ETH to ZEENUS Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_zeen_receipt.gasUsed,
        mc_zeen_receipt.gasUsed * ETH.GAS_GWEI,
        mc_zeen_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))

    gas				= 25000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    src_pre_ween_bal		= w3.eth.get_balance( src )
    mc_ween_balance		= WEEN_IERC20.functions.balanceOf( src ).call({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    src_pre_zeen_bal		= w3.eth.get_balance( src )
    print( "{:10}: Web3 Tester WEENUS.balanceOf({}) == {!r} Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet, src, mc_ween_balance,
        ( src_pre_ween_bal - src_pre_zeen_bal ),
        ( src_pre_ween_bal - src_pre_zeen_bal ) * ETH.GAS_GWEI,
        ( src_pre_ween_bal - src_pre_zeen_bal ) * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))

    mc_zeen_balance		= ZEEN_IERC20.functions.balanceOf( src ).call({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    src_aft_zeen_bal		= w3.eth.get_balance( src )
    print( "{:10}: Web3 Tester ZEENUS.balanceOf({}) == {!r} Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet, src, mc_zeen_balance,
        ( src_aft_zeen_bal - src_pre_zeen_bal ),
        ( src_aft_zeen_bal - src_pre_zeen_bal ) * ETH.GAS_GWEI,
        ( src_aft_zeen_bal - src_pre_zeen_bal ) * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))

    # So, just send some ETH to the forwarder address from the default account.  This will *not*
    # trigger any function, and should be low-cost (a regular ETH transfer), like ~21,000 gas.
    gas				= 25000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_send_hash		= w3.eth.send_transaction({
        'to':		mc_fwd0_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	w3.to_wei( .01, 'ether' )
    } | gas_price )
    print( f"{testnet:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 hash: {mc_send_hash.hex()}" )
    mc_send			= w3.eth.get_transaction( mc_send_hash )
    print( f"{testnet:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 transaction: {json.dumps( mc_send, indent=4, default=str )}" )

    mc_send_receipt		= w3.eth.wait_for_transaction_receipt( mc_send_hash )
    print( f"{testnet:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 receipt: {json.dumps( mc_send_receipt, indent=4, default=str ) }" )
    print( "{:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_send_receipt.gasUsed,
        mc_send_receipt.gasUsed * ETH.GAS_GWEI,
        mc_send_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))

    # Also send some (10% of *EENUS) ERC-20 tokens to the forwarder address.  ZEENUS is a 0-decimal
    # token, so the amounts will not round the same as WEENUS (an 18-decimal token). TODO: since we
    # divide by the denominator first (losing precision), we could check if the value is below
    # max/scale and change the order...  Done.  Confirm mc_*een_paid gets correctly split between the
    # final target accounts, according to the ratios in addr_frac.
    gas				= 150000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet

    mc_ween_paid		= mc_ween_balance // 10
    mc_fwd0_ween_hash		= WEEN_IERC20.functions.transfer( mc_fwd0_addr, mc_ween_paid ).transact({
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    mc_fwd0_ween_tx		= w3.eth.get_transaction( mc_fwd0_ween_hash )
    mc_fwd0_ween_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_ween_hash )
    print( "{:10}: Web3 Tester Forward#0 WEENUS transfer Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_ween_receipt.gasUsed,
        mc_fwd0_ween_receipt.gasUsed * ETH.GAS_GWEI,
        mc_fwd0_ween_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))

    mc_zeen_paid		= mc_zeen_balance // 10
    mc_fwd0_zeen_hash		= ZEEN_IERC20.functions.transfer( mc_fwd0_addr, mc_zeen_paid ).transact({
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    mc_fwd0_zeen_tx		= w3.eth.get_transaction( mc_fwd0_zeen_hash )
    mc_fwd0_zeen_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_zeen_hash )
    print( "{:10}: Web3 Tester Forward#0 ZEENUS transfer Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_zeen_receipt.gasUsed,
        mc_fwd0_zeen_receipt.gasUsed * ETH.GAS_GWEI,
        mc_fwd0_zeen_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))


    gas				= 25000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-send ETH/*EENUS ERC-20 to Forwarder#0:" )
    for a in ( src, ) + tuple( destination ) + ( mc_cons_addr, ) + ( mc_fwd0_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ('fwd' if a == mc_fwd0_addr else ('payout' if a == mc_cons_addr else ''))}" )
        if ( wbal := WEEN_IERC20.functions.balanceOf( a ).call({
                'nonce':	w3.eth.get_transaction_count( src ),
                'gas':		gas,
        } | gas_price )):
            print( f"  o WEENUS ERC-20 == {wbal:23} == {wbal/WEEN_DEN:9,.2f}" )
        if ( zbal := ZEEN_IERC20.functions.balanceOf( a ).call({
                'nonce':	w3.eth.get_transaction_count( src ),
                'gas':		gas,
        } | gas_price )):
            print( f"  o ZEENUS ERC-20 == {zbal:23} == {zbal/ZEEN_DEN:9,.2f}" )

    # Instantiate the ...Forwarder#0 again; should re-create at the exact same address.
    gas				= 500000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_fwd0_agin_hash		= multipayout_ERC20.functions.forwarder( 0 ).transact({
        'to':		mc_cons_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    mc_fwd0_agin_tx		= w3.eth.get_transaction( mc_fwd0_agin_hash )
    mc_fwd0_agin_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_agin_hash )
    print( "{:10}: Web3 Tester Forward#0 forwarder Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_agin_receipt.gasUsed,
        mc_fwd0_agin_receipt.gasUsed * ETH.GAS_GWEI,
        mc_fwd0_agin_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))
    # How do we harvest the result from the tx/receipt?
    #assert mc_fwd0_addr_again == mc_fwd0_addr

    gas				= 25000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-instantiate Forwarder#0 again:" )
    for a in ( src, ) + tuple( destination ) + ( mc_cons_addr, ) + ( mc_fwd0_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ('fwd' if a == mc_fwd0_addr else ('payout' if a == mc_cons_addr else ''))}" )
        if ( wbal := WEEN_IERC20.functions.balanceOf( a ).call({
                'nonce':	w3.eth.get_transaction_count( src ),
                'gas':		gas,
        } | gas_price )):
            print( f"  o WEENUS ERC-20 == {wbal:23} == {wbal/WEEN_DEN:9,.2f}" )
        if ( zbal := ZEEN_IERC20.functions.balanceOf( a ).call({
                'nonce':	w3.eth.get_transaction_count( src ),
                'gas':		gas,
        } | gas_price )):
            print( f"  o ZEENUS ERC-20 == {zbal:23} == {zbal/ZEEN_DEN:9,.2f}" )

    # Finally, invoke the payout function.
    gas				= 500000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_payo_hash		= multipayout_ERC20.functions.payout().transact({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    print( f"{testnet:10}: Web3 Tester payout MultiPayoutERC20 hash: {mc_payo_hash.hex()}" )

    mc_payo_receipt		= w3.eth.wait_for_transaction_receipt( mc_payo_hash )
    print( f"{testnet:10}: Web3 Tester payout MultiPayoutERC20: {json.dumps( mc_payo_receipt, indent=4, default=str )}" )

    print( "{:10}: Web3 Tester payout MultiPayoutERC20 Gas Used: {} == {}gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_payo_receipt.gasUsed,
        mc_payo_receipt.gasUsed * ETH.GAS_GWEI,
        mc_payo_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))
    print( "{:10}: Web3 Tester payout MultiPayoutERC20 PayoutETH events: {}".format(
        testnet,
        json.dumps(
            multipayout_ERC20.events['PayoutETH']().processReceipt( mc_payo_receipt, errors=web3_logs.WARN ),
            indent=4, default=str,
        )
    ))
    print( "{:10}: Web3 Tester payout MultiPayoutERC20 PayoutERC20 events: {}".format(
        testnet,
        json.dumps(
            multipayout_ERC20.events['PayoutERC20']().processReceipt( mc_payo_receipt, errors=web3_logs.WARN ),
            indent=4, default=str,
        )
    ))

    gas				= 25000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-payout ETH:" )
    for a in ( src, ) + tuple( destination ) + ( mc_cons_addr, ) + ( mc_fwd0_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ('fwd' if a == mc_fwd0_addr else ('payout' if a == mc_cons_addr else ''))}" )
        if ( wbal := WEEN_IERC20.functions.balanceOf( a ).call({
                'nonce':	w3.eth.get_transaction_count( src ),
                'gas':		gas,
        } | gas_price )):
            print( f"  o WEENUS ERC-20 == {wbal:23} == {wbal/WEEN_DEN:9,.2f}" )
        if ( zbal := ZEEN_IERC20.functions.balanceOf( a ).call({
                'nonce':	w3.eth.get_transaction_count( src ),
                'gas':		gas,
        } | gas_price )):
            print( f"  o ZEENUS ERC-20 == {zbal:23} == {zbal/ZEEN_DEN:9,.2f}" )

    # Finally, the Forwarder and Contract addresses should be empty!
    assert w3.eth.get_balance( mc_fwd0_addr ) == 0
    assert w3.eth.get_balance( mc_cons_addr ) == 0
