
import json
import os
import random

from textwrap		import indent

import pytest
from string		import Template

import rlp
import solcx

from web3		import Web3, logs as web3_logs
from web3.contract	import normalize_address_no_ens
from web3.middleware	import construct_sign_and_send_raw_middleware
from eth_account	import Account

from ..util		import remainder_after, into_bytes
from ..api		import (
    account, accounts,
)

from .			import precomputed_contract_address
from .multisend		import (
    make_trustless_multisend, build_recursive_multisend, simulate_multisends,
)

from .ethereum		import Etherscan as ETH  # Eg. ETH.GWEI_GAS, .ETH_USD


# Optimize, and search for imports relative to this directory
solcx_options			= dict(
    optimize		= True,
    optimize_runs	= 100000,
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





multipayout_defaults	= {
    '0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b':  6.90 / 100,
    '0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B': 40.00 / 100,
    '0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955': 53.10 / 100,
}




#
# Lets deduce the accounts to use in the Goerli Ethereum testnet.  Look for environment variables:
#
#   GOERLI_XPRVKEY	- Use this xprv... key to generate m/../0/0 (source) and m/../0/1-3 (destination) addresses
#   GOERLI_SEED		- Use this Seed (eg. BIP-39 Mnemonic Phrase, hex seed, ...) to generate the xprvkey
#
# If neither of those are found, use the 128-bit ffff...ffff Seed entropy.  Once you provision an
# xprvkey and derive the .../0/0 address, send some Goerli Ethereum testnet ETH to it.
#
# With no configuration, we'll end up using the 128-bit ffff...ffff Seed w/ no BIP-39 encoding as
# our root HD Wallet seed.
#
goerli_targets			= 3
goerli_xprvkey			= os.getenv( 'GOERLI_XPRVKEY' )
if not goerli_xprvkey:
    goerli_seed			= os.getenv( 'GOERLI_SEED' )
    if goerli_seed:
        try:
            goerli_xprvkey	= account( goerli_seed, crypto="ETH", path="m/44'/1'/0'" ).xprvkey
        except Exception:
            pass

goerli_src, goerli_destination	= None,[]
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


solc_multipayout_web3_tests	= [
    (
        "Tester",
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
]
if goerli_xprvkey:
    solc_multipayout_web3_tests += [(
        # Web3.HTTPProvider( f"https://eth-goerli.g.alchemy.com/v2/{os.getenv( 'ALCHEMY_API_TOKEN' )}" ),
        "Goerli",
        Web3.WebsocketProvider( f"wss://eth-goerli.g.alchemy.com/v2/{os.getenv( 'ALCHEMY_API_TOKEN' )}" ),
        goerli_src.address, goerli_src.prvkey, goerli_destination,
    )]


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
# Single Use Address "Vault"
# --------------------------
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
multipayout_ERC20_template	= Template( r"""
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "openzeppelin-contracts/contracts/security/ReentrancyGuard.sol";
import "openzeppelin-contracts/contracts/access/Ownable.sol";
import "openzeppelin-contracts/contracts/interfaces/IERC20.sol";

import "contracts/MultiPayoutERC20Base.sol";
import "contracts/MultiPayoutERC20Forwarder.sol";

contract MultiPayoutERC20 is MultiPayoutERC20Base {

    event PayoutETH( uint256 value, address to, bool sent );
    event PayoutERC20( uint256 value, address to, bool sent, IERC20 token );

    //
    // constructor (establishes unique contract creation bytcode by demanding owner supply their address)
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
       address			_self,
       IERC20[] memory		_erc20s
    )
       payable
    {
        require( _self == owner() );
        for ( uint256 t = 0; t < _erc20s.length; t++ ) {
            erc20s_add( _erc20s[t] );
        }
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
     */
    receive() external payable { }

    fallback() external payable { }

    //
    // Anyone can instantiate a forwarder; it can only forward the address' ETH/ERC-20 tokens
    // to this very contract.  So: fill your boots.  So long as the ERC-20 tokens supported
    // by this Contract are only settable by the Owner, it should be safe.
    //
    function forwarder(
         uint256		_salt
    )
        external
        returns ( address )
    {
        return address( new MultiPayoutERC20Forwarder{ salt: bytes32( _salt ) }( payable( address( this ))));
    }

    function forwarder_address(
        uint256			_salt
    )
        external
        view
        returns ( address )
    {
        bytes memory bytecode	= type(MultiPayoutERC20Forwarder).creationCode;
        bytes memory creation	= abi.encodePacked( bytecode, abi.encode( address( this )));
        bytes32 creation_hash	= keccak256(
            abi.encodePacked( bytes1( 0xff ), address( this ), bytes32( _salt ), keccak256( creation ))
        );
        return address( uint160( uint256( creation_hash )));
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

    function value_reserve_x10k( uint256 _value, uint16 _leave_x10k ) private view returns ( uint256 ) {
        uint256 reserve		= (
            _leave_x10k > 0
            ? (
                _value > type(uint256).max / 10000
                ? type(uint256).max / 10000
                : _value * _leave_x10k / 10000
              )
            : 0
        );
        return _value - reserve;
    }

    function transfer_except_ERC20( IERC20 erc20, address payable to, uint16 reserve_x10k ) private {
        uint256 tok_balance;
        try erc20.balanceOf( address( this )) returns ( uint256 v ) {
            tok_balance		= v;
        } catch {
            return;
        }
        if ( tok_balance > 0 ) {
            uint256 tok_value	= value_reserve_x10k( tok_balance, reserve_x10k );
            if ( tok_value > 0 ) {
                bool tok_sent;
                try erc20.transfer( to, tok_value ) returns ( bool s ) {
                    tok_sent	= s;
                } catch {
                    return;
                }
                emit PayoutERC20( tok_value, to, tok_sent, erc20 );
            }
        }
    }

    function transfer_except( address payable to, uint16 reserve_x10k ) private {
        for ( uint256 t = 0; t < erc20s.length; t++ ) {
            transfer_except_ERC20( erc20s[t], to, reserve_x10k );
        }
        uint256 eth_value	= value_reserve_x10k( address( this ).balance, reserve_x10k );
        (bool eth_sent, )   	= to.call{ value: eth_value }( "" );
        emit PayoutETH( eth_value, to, eth_sent );
    }

    //
    // payout_internal Executes the ERC-20 / ETH transfers to the predefined accounts / fractions
    //
    function payout_internal() private {
${RECIPIENTS}
    }
}
""" )


def multipayout_ERC20_recipients( addr_frac, scale=10000 ):
    """Produce recipients array elements w/ fixed fractional amounts to predefined addresses.  Convert in the
    range (0,1) totalling to exactly 1.0 to within a multiple of scale, or will raise Exception.

    Packs address + fixed-point fraction (x10k) into a uint176 sufficient to hold:

       bytes bits  description
       ----- ----  -----------
         20   160  Address of recipient
          2    16  Fraction to reserve (x10,000)
        ---   ---
         22   176

    similar to:

        https://github.com/Alonski/MultiSendEthereum/blob/master/contracts/MultiSend.sol

    except using uints instead of bytes, so Solidity >= 0.8 'constant' data is used (avoiding
    expensive SSTORE)

    Also supports a predefined number of ERC-20 tokens, which are also distributed according to the
    specified fractions.


    """
    addr_frac_sorted		= sorted( addr_frac.items(), key=lambda a_p: a_p[1] )
    i, frac_total		= 0, 0
    payout			= ""
    for i,((addr,frac),rem) in enumerate( zip(
            addr_frac_sorted,
            remainder_after( f for _,f in addr_frac_sorted )
    )):
        frac_total	       += frac
        rem_scale		= int( rem * scale )
        payout		       += f"transfer_except( payable( address( {normalize_address_no_ens( addr )} )), uint16( {rem_scale:>{len(str(scale))}} ));  // {frac*100:6.2f}%\n"
    assert i > 0 and 1 - 1/scale < frac_total < 1 + 1/scale and rem_scale == 0, \
        f"Total payout percentages didn't sum to 100%: {frac_total*100:9.4f}%; remainder: {rem:7.4f} x {scale}: {rem_scale}"
    return payout


def test_multipayout_ERC20_recipients():
    payout			= multipayout_ERC20_recipients( multipayout_defaults )
    print()
    print( payout )
    assert payout == """\
transfer_except( payable( address( 0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b )), uint16(  9310 ));  //   6.90%
transfer_except( payable( address( 0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B )), uint16(  5703 ));  //  40.00%
transfer_except( payable( address( 0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955 )), uint16(     0 ));  //  53.10%
"""


def multipayout_ERC20_solidity( addr_frac ):
    recipients			= multipayout_ERC20_recipients( addr_frac )
    prefix			= ' ' * 8
    return multipayout_ERC20_template.substitute(
        RECIPIENTS	= indent( recipients, prefix ),
    )


HOT			= "0x6c6EE5e31d828De241282B9606C8e98Ea48526E2"
USDT			= "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDT_GOERLI		= "0xe802376580c10fE23F027e1E19Ed9D54d4C9311e"
USDC			= "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
USDC_GOERLI		= "0xde637d4C445cA2aae8F782FFAc8d2971b93A4998"


def test_multipayout_ERC20_solidity():
    solidity			= multipayout_ERC20_solidity(
        addr_frac	= multipayout_defaults,
    )
    print()
    print( solidity )



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
    assert precopmuted_contract_address( address, salt, contract ) == expected_address


@pytest.mark.parametrize( "testnet, provider, src, src_prvkey, destination", solc_multipayout_web3_tests )
def test_solc_multipayout_ERC20_web3_tester( testnet, provider, src, src_prvkey, destination ):
    """Use web3 tester

    """
    print( f"{testnet:10}: Web3( {provider!r} ): Source ETH account: {src} (private key: {src_prvkey}; destination: {', '.join( destination )}" )

    solc_version		= "0.8.17"
    solcx.install_solc( version=solc_version )

    # Fire up Web3, and get the list of accounts we can operate on
    w3				= Web3( provider )

    latest			= w3.eth.get_block('latest')
    print( f"{testnet:10}: Web3 Latest block: {json.dumps( latest, indent=4, default=str )}" )

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

    # Generate a contract targeting these destination accounts, with random percentages.
    addr_frac			= {
        addr: random.random()
        for addr in destination
    }
    unitize			= sum( addr_frac.values() )
    addr_frac			= {
        addr: frac / unitize
        for addr,frac in addr_frac.items()
    }
    # Must be actual ERC-20 contracts; if these fail to have a .balanceOf or .transfer API, this
    # contract will fail.  So, if an ERC-20 token contract is self-destructed, the
    # MultiTransferERC20 would begin to fail, unless we caught and ignored ERC-20 API exceptions.
    tokens			= [ USDT_GOERLI, USDC_GOERLI ]
    payout_sol			= multipayout_ERC20_solidity( addr_frac=addr_frac )
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

    mc_cons_hash		= MultiPayoutERC20.constructor( src, tokens ).transact({
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		2000000,
    })
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 hash: {mc_cons_hash.hex()}" )
    mc_cons			= w3.eth.get_transaction( mc_cons_hash )
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 transaction: {json.dumps( mc_cons, indent=4, default=str )}" )

    mc_cons_receipt		= w3.eth.wait_for_transaction_receipt( mc_cons_hash )
    multipayout_ERC20_address	= mc_cons_receipt.contractAddress

    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 receipt: {json.dumps( mc_cons_receipt, indent=4, default=str )}" )
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 Contract: {len( bytecode)} bytes, at Address: {multipayout_ERC20_address}" )
    print( "{:10}: Web3 Tester Construct MultiPayoutERC20 Gas Used: {} == {}gwei == USD${:7.2f} ({}): ${:7.6f}/byte".format(
        testnet,
        mc_cons_receipt.gasUsed,
        mc_cons_receipt.gasUsed * ETH.GAS_GWEI,
        mc_cons_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
        mc_cons_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI / len( bytecode ),
    ))

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-contract creation:" )
    for a in ( src, ) + tuple( destination ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

    multipayout_ERC20		= w3.eth.contract(
        address	= mc_cons_receipt.contractAddress,
        abi	= abi,
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
    fwd_creation_code		= MultiPayoutERC20Forwarder.constructor( multipayout_ERC20_address ).data_in_transaction;

    # 3) Compute the 0th MultiPayoutERC20Forwarder Contract address, targeting this MultiPayoutERC20 Contract.
    salt_0			= w3.codec.encode( [ 'uint256' ], [ 0 ] )
    mc_fwd0_addr_precomputed	= precomputed_contract_address(
        address		= multipayout_ERC20_address,
        salt		= salt_0,
        creation	= fwd_creation_code,
    )
    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address: {mc_fwd0_addr_precomputed} (precomputed)" )

    mc_fwd0_aclc_hash		= MultiPayoutERC20.functions.forwarder_address( 0 ).transact({
        'to':		mc_cons_receipt.contractAddress,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gasPrice':	w3.eth.gas_price,
        'gas':		250000,
        'value':	0,
    })
    mc_fwd0_aclc_tx		= w3.eth.get_transaction( mc_fwd0_aclc_hash )
    mc_fwd0_aclc_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_aclc_hash )
    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address Receipt: {json.dumps( mc_fwd0_aclc_receipt, indent=4, default=str )} (calculated)" )
    mc_fwd0_aclc_result		= multipayout_ERC20.functions.forwarder_address( 0 ).call({
        'to':		mc_cons_receipt.contractAddress,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gasPrice':	w3.eth.gas_price,
        'gas':		250000,
        'value':	0,
    })
    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address: {mc_fwd0_aclc_result} (calculated)" )

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 pre-instantiate Forwarder#0:" )
    for a in ( src, ) + tuple( destination ) + ( mc_fwd0_addr_precomputed, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

    # Lets actually deploy the 0th MultiPayoutERC20Forwarder and confirm that it is created at the
    # expected address.
    mc_fwd0_addr		= multipayout_ERC20.functions.forwarder( 0 ).call({
        'to':		mc_cons_receipt.contractAddress,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gasPrice':	w3.eth.gas_price,
        'gas':		500000,
    })
    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address: {mc_fwd0_addr} (instantiated)" )

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 pre-instantiate Forwarder#0:" )
    for a in ( src, ) + tuple( destination ) + ( mc_fwd0_addr_precomputed, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

    assert mc_fwd0_addr == mc_fwd0_aclc_result == mc_fwd0_addr_precomputed

    # TODO: send some ETH and ERC-20s to the Forwarder address and re-deploy the contract


    # So, just send some ETH from the default account.  This will *not* trigger the payout function,
    # and should be low-cost (a regular ETH transfer), like ~21,000 gas.
    mc_send_hash		= w3.eth.send_transaction({
        'to':		mc_fwd0_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gasPrice':	w3.eth.gas_price,
        'gas':		250000,
        'value':	w3.to_wei( .01, 'ether' )
    })
    print( f"{testnet:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 hash: {mc_send_hash.hex()}" )
    mc_send			= w3.eth.get_transaction( mc_send_hash )
    print( f"{testnet:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 transaction: {json.dumps( mc_send, indent=4, default=str )}" )

    mc_send_receipt		= w3.eth.wait_for_transaction_receipt( mc_send_hash )
    print( f"{testnet:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 receipt: {json.dumps( mc_send_receipt, indent=4, default=str ) }" )
    print( "{:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 Gas Used: {} == {}gwei == USD${:7.2f} ({})".format(
        testnet,
        mc_send_receipt.gasUsed,
        mc_send_receipt.gasUsed * ETH.GAS_GWEI,
        mc_send_receipt.gasUsed * ETH.GAS_GWEI * ETH.ETH_USD / ETH.ETH_GWEI, ETH.STATUS or 'estimated',
    ))

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-send ETH to Forwarder#0:" )
    for a in ( src, ) + tuple( destination ) + ( mc_fwd0_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

    # Instantiate the ...Forwarder#0 again; should re-create at the exact same address
    mc_fwd0_addr_again		= multipayout_ERC20.functions.forwarder( 0 ).call({
        'to':		mc_cons_receipt.contractAddress,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gasPrice':	w3.eth.gas_price,
        'gas':		500000,
    })
    assert mc_fwd0_addr_again == mc_fwd0_addr

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-instantiate Forwarder#0 again:" )
    for a in ( src, ) + tuple( destination ) + ( mc_fwd0_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )

    # Finally, invoke the payout function.
    mc_payo_hash		= multipayout_ERC20.functions.payout().transact({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		500000,
    })
    print( f"{testnet:10}: Web3 Tester payout MultiPayoutERC20 hash: {mc_payo_hash.hex()}" )

    mc_payo_receipt		= w3.eth.wait_for_transaction_receipt( mc_payo_hash )
    print( f"{testnet:10}: Web3 Tester payout MultiPayoutERC20: {json.dumps( mc_payo_receipt, indent=4, default=str )}" )

    print( "{:10}: Web3 Tester payout MultiPayoutERC20 Gas Used: {} == {}gwei == USD${:7.2f} ({})".format(
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

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-payout ETH:" )
    for a in ( src, ) + tuple( destination ) + ( mc_fwd0_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ''}" )
