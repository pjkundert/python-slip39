
import json
import os
import random
import pytest

from hashlib		import sha256
from pathlib		import Path
from fractions		import Fraction

import solcx

from crypto_licensing	import licensing, ed25519

from web3		import Web3, logs as web3_logs
from web3._utils.normalizers import normalize_address_no_ens
from web3.middleware	import construct_sign_and_send_raw_middleware
from eth_account	import Account

from .			import contract_address
from .ethereum		import Etherscan, Chain, alchemy_url
from .multipayout	import MultiPayoutERC20, payout_reserve
from ..api		import account, accounts


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


def test_solcx_smoke():
    solcx.install_solc( version="0.7.0" )
    contract_0_7_0 = solcx.compile_source(
        "contract Foo { function bar() public { return; } }",
        output_values=["abi", "bin-runtime"],
        solc_version="0.7.0",
        **solcx_options
    )
    assert contract_0_7_0 == {
        '<stdin>:Foo': {
            'abi': [{'inputs': [], 'name': 'bar', 'outputs': [], 'stateMutability': 'nonpayable', 'type': 'function'}],
            'bin-runtime': '6080604052348015600f57600080fd5b506004361060285760003560e01c8063febb0f7e14602d575b600080fd5b60336035565b005b56fea26469706673582212201e14b70708f9dab59194917fad07f469a23ebc424ad2213961b86d418988729764736f6c63430007000033'  # noqa: E501
        },
    }


#
# Lets deduce the accounts to use in the Goerli Ethereum testnet.  Look for environment variables:
#
#   ..._XPRVKEY		- Use this xprv... key to generate m/../0/0 (source) and m/../0/1-3 (destination) addresses
#   ..._SEED		- Use this Seed (eg. BIP-39 Mnemonic Phrase, hex seed, ...) to generate the xprvkey
#
# If neither of those are found, use the 128-bit ffff...ffff Seed entropy.  Once you provision an
# xprvkey and derive the .../0/0 address, send some Goerli Ethereum testnet ETH (TGOR) to it.
#
# With no configuration, we'll end up using the 128-bit ffff...ffff Seed w/ no BIP-39 encoding as
# our root HD Wallet seed.
#
# However, we will choose to *not* run the Multipayout tests, if no _SEED or _XPRVKEY is present,
# since they require/use resources in the test networks...
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
            # why m/44'/1'?  Dunno.  That's the derivation path Trezor Suite uses for Goerli wallets...
            goerli_xprvkey	= account( goerli_seed, crypto="ETH", path="m/44'/1'/0'" ).xprvkey
        except Exception:
            pass

if goerli_xprvkey:
    # the Account.address/.key
    goerli_src			= account( goerli_xprvkey, crypto='ETH', path="m/0/0" )
    #print( f"Goerli Ethereum Testnet src ETH address: {goerli_src.address}" )
    # Just addresses
    goerli_destination		= tuple(
        a.address
        for a in accounts( goerli_xprvkey, crypto="ETH", paths=f"m/0/1-{goerli_targets}" )
    )
    #print( f"Goerli Ethereum Testnet dst ETH addresses: {json.dumps( goerli_destination, indent=4 )}" )

    web3_testers	       += [(
        "Goerli",
        Web3.WebsocketProvider(
            alchemy_url( Chain.Goerli )  # f"wss://eth-goerli.g.alchemy.com/v2/{os.getenv( 'ALCHEMY_API_TOKEN' )}"
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
    #print( f"Goerli Ethereum Testnet src ETH address: {ganache_src.address}" )
    # Just addresses
    ganache_destination		= tuple(
        a.address
        for a in accounts( ganache_xprvkey, crypto="ETH", paths=f"m/0/1-{ganache_targets}" )
    )
    #print( f"Ganache Ethereum Testnet dst ETH addresses: {json.dumps( ganache_destination, indent=4 )}" )

    web3_testers		       += [(
        "Ganache",
        Web3.HTTPProvider(					# Provider and chain_id (if any)
            f"http://127.0.0.1:{os.getenv( 'GANACHE_PORT', 7545 )}",
        ), int( os.getenv( 'GANACHE_NETWORK_ID' ) or 5777 ),
        ganache_src.address, ganache_src.prvkey, ganache_destination,
    ),]


def multipayout_ERC20_recipients( addr_frac, bits=16 ):
    """We used to generate contract code directly; still use for testing underlying functionality."""
    payout			= ""
    for addr,frac,rem in payout_reserve( addr_frac, bits=bits ):
        pct			= f"{float( frac * 100 ):9.5f}%"
        payout		       += f"transfer_except( payable( address( {normalize_address_no_ens( addr )} )), uint{bits}( {int( rem ):>{len(str(2**bits))}} ));  // {pct}\n"
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
    #print()
    #print( payout )
    assert payout == """\
transfer_except( payable( address( 0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b )), uint16( 61014 ));  //   6.90000%
transfer_except( payable( address( 0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B )), uint16( 37378 ));  //  40.00000%
transfer_except( payable( address( 0xa29618aBa937D2B3eeAF8aBc0bc6877ACE0a1955 )), uint16(     0 ));  //  53.10000%
"""


@pytest.mark.parametrize( "multipayout_defaults, expected", [
    (
        # Tiny recipients that round to almost zero receive the smallest representable proportion
        {
            '0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b': 1,
            '0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B': 100000,
        },"""\
transfer_except( payable( address( 0x7F7458EF9A583B95DFD90C048d4B2d2F09f6dA5b )), uint16( 65535 ));  //   0.00100%
transfer_except( payable( address( 0x94Da50738E09e2f9EA0d4c15cf8DaDfb4CfC672B )), uint16(     0 ));  //  99.99900%
"""
    ),
])
def test_multipayout_ERC20_recipients_corner( multipayout_defaults, expected ):
    assert multipayout_ERC20_recipients( multipayout_defaults ) == expected


@pytest.mark.parametrize('address, salt, creation, expected_address', [
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
def test_create2(address, salt, creation, expected_address):
    """Test the CREATE2 opcode Python implementation.

    EIP-104 https://github.com/ethereum/EIPs/blob/master/EIPS/eip-1014.md

    """
    assert contract_address( address, salt=salt, creation=creation ) == expected_address


@pytest.mark.parametrize('address, nonce, expected_address', [
    (
        '0x6ac7ea33f8831ea9dcc53393aaa88b25a785dbf0',
        0,
        '0xcd234A471b72ba2F1Ccf0A70FCABA648a5eeCD8d',
    ),
    (
        '0x6ac7ea33f8831ea9dcc53393aaa88b25a785dbf0',
        1,
        '0x343c43A37D37dfF08AE8C4A11544c718AbB4fCF8',
    ),
])
def test_create(address, nonce, expected_address):
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
# The funds came from the 0x667A... (the "zoo zoo ... wrong") source account, and were:
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
@pytest.mark.skipif( not goerli_xprvkey and not ganache_xprvkey,
                     reason="Specify {GOERLI,GANACHE}_{SEED,XPRVKEY} to run MultiPayoutERC20 tests" )
@pytest.mark.parametrize( "testnet, provider, chain_id, src, src_prvkey, destination", web3_testers )
def test_multipayout_ERC20_web3_tester( testnet, provider, chain_id, src, src_prvkey, destination ):
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

    def gas_pricing(
        of		= f"{testnet:10}: Web3 Tester",
        gas		= None,
        **kwds,
    ):
        """Estimate what the gas will cost in USD$, given the transaction's parameters (None if unknown).

        Defaults to the gas of a standard ETH transfer.

        If an old-style fixed gasPrice is given, use that.

        Otherwise, looks for EIP-1559 maxPriorityFeePerGas and maxFeePerGas.

        """
        if gas is None:
            gas			= 21000
        if 'gasPrice' in kwds:
            # Old fixed gas pricing
            est_gas_wei		= int(kwds['gasPrice'])
            max_cost_gwei	= int(gas) * est_gas_wei / ETH.GWEI_WEI
            max_cost_eth	= max_cost_gwei / ETH.ETH_GWEI
            max_cost_usd	= max_cost_eth * ETH.ETH_USD
            print( "{} Gas Price at USD${:9,.2f}/ETH: fee wei/gas fixed {:.4f}: cost per {:,d} Gas: {:,.4f} gwei == {:,.6f} ETH == USD${:10,.6f} ({})".format(  # noqa: E501
                of,
                ETH.ETH_USD,
                est_gas_wei,
                int(gas),
                max_cost_gwei,
                max_cost_eth,
                max_cost_usd,
                ETH.STATUS or 'estimated',
            ))
        elif 'maxFeePerGas' in kwds or 'baseFeePerGas' in kwds:
            # New EIP-1599 gas pricing
            max_gas_wei		= int(kwds.get( 'maxFeePerGas', kwds.get( 'baseFeePerGas' )))
            max_cost_gwei	= int(gas) * max_gas_wei / ETH.GWEI_WEI
            max_cost_eth	= max_cost_gwei / ETH.ETH_GWEI
            max_cost_usd	= max_cost_eth * ETH.ETH_USD
            print( "{} Gas Price at USD${:9,.2f}/ETH: fee gwei/gas max.  {:.4f}: cost per {:,d} Gas: {:,.4f} gwei == {:,.6f} ETH == USD${:10,.6f} ({})".format(  # noqa: E501
                of,
                ETH.ETH_USD,
                max_gas_wei,
                int(gas),
                max_cost_gwei,
                max_cost_eth,
                max_cost_usd,
                ETH.STATUS or 'estimated',
            ))
        else:
            max_cost_usd	= None  # Unknown
            print( "{} Gas Price at USD${:9,.2f}/ETH: fee gwei/gas unknown from {} ({})".format(  # noqa: E501
                of,
                ETH.ETH_USD,
                ', '.join( f"{k} == {v!r}" for k,v in kwds.items() ),
                ETH.STATUS or 'estimated',
            ))

        return max_cost_usd

    # Ask the connected Ethereum testnet what it thinks gas prices are.  This will
    # (usually) be a Testnet, where gas prices are artificially low vs. the real Ethereum
    # network.
    max_priority_fee		= w3.eth.max_priority_fee
    base_fee			= latest['baseFeePerGas']
    gas				= 21000

    gas_pricing(
        gas			= gas,
        maxPriorityFeePerGas	= max_priority_fee,
        baseFeePerGas		= base_fee,
    )

    max_gas_wei			= base_fee * 2 + max_priority_fee
    gas_price_testnet		= dict(
        maxFeePerGas		= max_gas_wei,		# If we want to fail if base fee + priority fee exceeds some limits
        maxPriorityFeePerGas	= max_priority_fee,
    )
    print( f"{testnet:10}: Gas Pricing EIP-1559 for max $1.50 per 21,000 Gas transaction (using Testnet Gas pricing): {json.dumps( gas_price_testnet )}" )

    # Let's say we're willing to pay up to $1.50 for a standard Ethereum transfer costing 21,000 gas
    max_usd_per_gas		= 1.50 / gas

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
        addr: Fraction( 1+random.choice( range( 1000 )))
        for addr in destination   # [random.choice(range(len(destination))):]   #for determinism keep all...
    }

    # Must be actual ERC-20 contracts; if these fail to have a .balanceOf or .transfer API, this
    # contract will fail.  So, if an ERC-20 token contract is self-destructed, the
    # MultiTransferERC20 would begin to fail, unless we caught and ignored ERC-20 API exceptions.
    tokens			= [ USDT_GOERLI, USDC_GOERLI, WEEN_GOERLI, ZEEN_GOERLI ]
    payees			= [
        (addr, int( rem ))
        for addr,frac,rem in payout_reserve( addr_frac )
    ]
    print( f"{testnet:10} Payees: {json.dumps( payees, indent=4, default=str )}" )

    #payout_sol			= multipayout_ERC20_solidity( addr_frac=addr_frac, bits=16 )
    #print( payout_sol )

    compiled_sol		= solcx.compile_files(
        Path( __file__ ).resolve().parent / 'contracts' / 'MultiPayoutERC20.sol',
        output_values	= ['abi', 'bin'],
        solc_version	= solc_version,
        **solcx_options
    )
    print( f"{testnet:10}: {json.dumps( compiled_sol, indent=4, default=str )}" )

    mp_ERC20_key,		= ( k for k in compiled_sol.keys() if k.endswith( ":MultiPayoutERC20" ))
    mp_ERC20_bytecode		= compiled_sol[mp_ERC20_key]['bin']
    mp_ERC20_abi		= compiled_sol[mp_ERC20_key]['abi']

    MultiPayoutERC20_contract	= w3.eth.contract( abi=mp_ERC20_abi, bytecode=mp_ERC20_bytecode )

    gas				= 1400000  # 1388019 Gas is actual cost, as of 20230910
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_cons_tx			= {
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price

    gas_pricing( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20", **mc_cons_tx)

    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 Tx (using {'Mainnet' if ETH.UPDATED else 'Testnet'} Gas pricing): {json.dumps(mc_cons_tx, indent=4)}" )
    # Let's see what this would cost, using the estimated gas:

    mc_cons_hash		= MultiPayoutERC20_contract.constructor( payees, tokens ).transact( mc_cons_tx )
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 hash: {mc_cons_hash.hex()}" )
    mc_cons			= w3.eth.get_transaction( mc_cons_hash )
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 transaction: {json.dumps( mc_cons, indent=4, default=str )}" )

    mc_cons_receipt		= w3.eth.wait_for_transaction_receipt( mc_cons_hash )
    mc_cons_addr		= mc_cons_receipt.contractAddress

    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 receipt: {json.dumps( mc_cons_receipt, indent=4, default=str )}" )
    print( f"{testnet:10}: Web3 Tester Construct MultiPayoutERC20 Contract: {len( mp_ERC20_bytecode)} bytes, at Address: {mc_cons_addr}" )

    def tx_gas_cost( tx, receipt ):
        """Compute a transaction's actual gas cost, in Wei.  We must get the block's baseFeePerGas, and
        add our transaction's "tip" maxPriorityFeePerGas.  All prices are in Wei/Gas.

        """
        block			= w3.eth.get_block( receipt.blockNumber )  # w/ Web3 Tester, may be None
        tx_idx			= receipt.transactionIndex
        base_fee		= block.baseFeePerGas
        prio_fee		= tx.maxPriorityFeePerGas
        print( f"{testnet:10}: Block {block.number!r:10} base fee: {base_fee/ETH.GWEI_WEI:7.4f}Gwei + Tx #{tx_idx!r:4} prio fee: {prio_fee/ETH.GWEI_WEI:7.4f}Gwei" )
        return base_fee + prio_fee

    gas_cost			= tx_gas_cost( mc_cons, mc_cons_receipt )
    print( "{:10}: Web3 Tester Construct MultiPayoutERC20 Gas Used: {} == {:7.4f}Gwei == USD${:10,.6f} ({}): ${:7.6f}/byte".format(
        testnet,
        mc_cons_receipt.gasUsed,
        mc_cons_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_cons_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
        mc_cons_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI / len( mp_ERC20_bytecode ),
    ))

    print( f"{testnet:10}: Web3 Tester Accounts; MultiPayoutERC20 post-contract creation:" )
    for a in ( src, ) + tuple( destination ) + ( mc_cons_addr, ):
        print( f"- {a} == {w3.eth.get_balance( a )} {'src' if a == src else ('payout' if a == mc_cons_addr else '')}" )

    MultiPayoutERC20_instance		= w3.eth.contract(
        address	= mc_cons_addr,
        abi	= mp_ERC20_abi,
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
    fwd_creation_code		= MultiPayoutERC20Forwarder.constructor( mc_cons_addr ).data_in_transaction

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
    mc_fwd0_aclc_hash		= MultiPayoutERC20_instance.functions.forwarder_allocate( 0 ).transact({
        'to':		mc_cons_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    mc_fwd0_aclc		= w3.eth.get_transaction( mc_fwd0_aclc_hash )
    mc_fwd0_aclc_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_aclc_hash )
    gas_cost			= tx_gas_cost( mc_fwd0_aclc, mc_fwd0_aclc_receipt )
    print( "{:10}: Web3 Tester Forward#0 forwarder_allocate w/o <data> Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_aclc_receipt.gasUsed,
        mc_fwd0_aclc_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_fwd0_aclc_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
    ))
    print( f"{testnet:10}: Web3 Tester Forward#0 forwarder_address w/o <data> Receipt: {json.dumps( mc_fwd0_aclc_receipt, indent=4, default=str )} (calculated)" )

    gas				= 250000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    # The result is the address associated with this salt
    mc_fwd0_aclc_result,mc_fwd0_aclc_data = MultiPayoutERC20_instance.functions.forwarder_allocate( 0 ).call({
        'to':		mc_cons_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    print( f"{testnet:10}: Web3 Tester Forward#0 MultiPayoutERC20 Contract Address (w/o <data>): {mc_fwd0_aclc_result} (calculated), and associated data: {mc_fwd0_aclc_data!r}" )

    gas				= 250000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_fwd0_aclc_hash_w		= MultiPayoutERC20_instance.functions.forwarder_allocate( 0, bytes.fromhex( '00'*31+'01' )).transact({
        'to':		mc_cons_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    mc_fwd0_aclc_w		= w3.eth.get_transaction( mc_fwd0_aclc_hash_w )
    mc_fwd0_aclc_receipt_w	= w3.eth.wait_for_transaction_receipt( mc_fwd0_aclc_hash_w )
    gas_cost			= tx_gas_cost( mc_fwd0_aclc_w, mc_fwd0_aclc_receipt_w )
    print( "{:10}: Web3 Tester Forward#0 forwarder_address w/  <data> Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_aclc_receipt_w.gasUsed,
        mc_fwd0_aclc_receipt_w.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_fwd0_aclc_receipt_w.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
    ))
    print( f"{testnet:10}: Web3 Tester Forward#0 forwarder_address w/  <data> Receipt: {json.dumps( mc_fwd0_aclc_receipt_w, indent=4, default=str )} (calculated)" )

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
    mc_fwd0_addr,mc_fwd0_data	= MultiPayoutERC20_instance.functions.forwarder( 0 ).call({
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
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    mc_ween_hash		= w3.eth.send_transaction({
        'to':		WEEN_GOERLI,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    mc_ween			= w3.eth.get_transaction( mc_ween_hash )
    mc_ween_receipt		= w3.eth.wait_for_transaction_receipt( mc_ween_hash )
    gas_cost			= tx_gas_cost( mc_ween, mc_ween_receipt )
    print( f"{testnet:10}: Web3 Tester Send ETH to WEENUS receipt: {json.dumps( mc_ween_receipt, indent=4, default=str ) }" )
    print( "{:10}: Web3 Tester Send ETH to WEENUS Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_ween_receipt.gasUsed,
        mc_ween_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_ween_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
    ))

    mc_zeen_hash		= w3.eth.send_transaction({
        'to':		ZEEN_GOERLI,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
        'value':	0,
    } | gas_price )
    mc_zeen			= w3.eth.get_transaction( mc_zeen_hash )
    mc_zeen_receipt		= w3.eth.wait_for_transaction_receipt( mc_zeen_hash )
    gas_cost			= tx_gas_cost( mc_zeen, mc_zeen_receipt )
    print( f"{testnet:10}: Web3 Tester Send ETH to ZEENUS receipt: {json.dumps( mc_zeen_receipt, indent=4, default=str ) }" )
    print( "{:10}: Web3 Tester Send ETH to ZEENUS Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_zeen_receipt.gasUsed,
        mc_zeen_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_zeen_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
    ))

    # Hmm; this should be free; make sure it is, by getting our balance before/after
    gas				= 25000
    spend			= gas * max_usd_per_gas
    gas_price			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas ) if ETH.UPDATED else gas_price_testnet
    src_pre_ween_bal		= w3.eth.get_balance( src )
    mc_ween_balance		= WEEN_IERC20.functions.balanceOf( src ).call({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    src_pre_zeen_bal		= w3.eth.get_balance( src )
    print( "{:10}: Web3 Tester WEENUS.balanceOf({}) == {!r} Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet, src, mc_ween_balance,
        ( src_pre_ween_bal - src_pre_zeen_bal ),
        ( src_pre_ween_bal - src_pre_zeen_bal ),
        ( src_pre_ween_bal - src_pre_zeen_bal ) * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
    ))

    mc_zeen_balance		= ZEEN_IERC20.functions.balanceOf( src ).call({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    src_aft_zeen_bal		= w3.eth.get_balance( src )
    print( "{:10}: Web3 Tester ZEENUS.balanceOf({}) == {!r} Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet, src, mc_zeen_balance,
        ( src_aft_zeen_bal - src_pre_zeen_bal ),
        ( src_aft_zeen_bal - src_pre_zeen_bal ),
        ( src_aft_zeen_bal - src_pre_zeen_bal ) * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
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

    mc_send			= w3.eth.get_transaction( mc_send_hash )
    mc_send_receipt		= w3.eth.wait_for_transaction_receipt( mc_send_hash )
    gas_cost			= tx_gas_cost( mc_send, mc_send_receipt )
    print( f"{testnet:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 receipt: {json.dumps( mc_send_receipt, indent=4, default=str ) }" )
    print( "{:10}: Web3 Tester Send ETH to MultiPayoutERC20Forwarder#0 Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_send_receipt.gasUsed,
        mc_send_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_send_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
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
    mc_fwd0_ween		= w3.eth.get_transaction( mc_fwd0_ween_hash )
    mc_fwd0_ween_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_ween_hash )
    gas_cost			= tx_gas_cost( mc_fwd0_ween, mc_fwd0_ween_receipt )
    print( "{:10}: Web3 Tester Forward#0 WEENUS transfer Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_ween_receipt.gasUsed,
        mc_fwd0_ween_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_fwd0_ween_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
    ))

    mc_zeen_paid		= mc_zeen_balance // 10
    mc_fwd0_zeen_hash		= ZEEN_IERC20.functions.transfer( mc_fwd0_addr, mc_zeen_paid ).transact({
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    mc_fwd0_zeen		= w3.eth.get_transaction( mc_fwd0_zeen_hash )
    mc_fwd0_zeen_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_zeen_hash )
    gas_cost			= tx_gas_cost( mc_fwd0_zeen, mc_fwd0_zeen_receipt )
    print( "{:10}: Web3 Tester Forward#0 ZEENUS transfer Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_zeen_receipt.gasUsed,
        mc_fwd0_zeen_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_fwd0_zeen_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
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
    mc_fwd0_agin_hash		= MultiPayoutERC20_instance.functions.forwarder( 0 ).transact({
        'to':		mc_cons_addr,
        'from':		src,
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    mc_fwd0_agin		= w3.eth.get_transaction( mc_fwd0_agin_hash )
    mc_fwd0_agin_receipt	= w3.eth.wait_for_transaction_receipt( mc_fwd0_agin_hash )
    gas_cost			= tx_gas_cost( mc_fwd0_agin, mc_fwd0_agin_receipt )
    print( "{:10}: Web3 Tester Forward#0 forwarder Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_fwd0_agin_receipt.gasUsed,
        mc_fwd0_agin_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_fwd0_agin_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
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
    mc_payo_hash		= MultiPayoutERC20_instance.functions.payout().transact({
        'nonce':	w3.eth.get_transaction_count( src ),
        'gas':		gas,
    } | gas_price )
    print( f"{testnet:10}: Web3 Tester payout MultiPayoutERC20 hash: {mc_payo_hash.hex()}" )

    mc_payo			= w3.eth.get_transaction( mc_payo_hash )
    mc_payo_receipt		= w3.eth.wait_for_transaction_receipt( mc_payo_hash )
    gas_cost			= tx_gas_cost( mc_payo, mc_payo_receipt )
    print( f"{testnet:10}: Web3 Tester payout MultiPayoutERC20: {json.dumps( mc_payo_receipt, indent=4, default=str )}" )

    print( "{:10}: Web3 Tester payout MultiPayoutERC20 Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({})".format(
        testnet,
        mc_payo_receipt.gasUsed,
        mc_payo_receipt.gasUsed * gas_cost / ETH.GWEI_WEI,
        mc_payo_receipt.gasUsed * gas_cost * ETH.ETH_USD / ETH.ETH_WEI, ETH.STATUS or 'estimated',
    ))
    print( "{:10}: Web3 Tester payout MultiPayoutERC20 PayoutETH events: {}".format(
        testnet,
        json.dumps(
            MultiPayoutERC20_instance.events['PayoutETH']().process_receipt( mc_payo_receipt, errors=web3_logs.WARN ),
            indent=4, default=str,
        )
    ))
    print( "{:10}: Web3 Tester payout MultiPayoutERC20 PayoutERC20 events: {}".format(
        testnet,
        json.dumps(
            MultiPayoutERC20_instance.events['PayoutERC20']().process_receipt( mc_payo_receipt, errors=web3_logs.WARN ),
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


@pytest.mark.skipif( not goerli_xprvkey and not ganache_xprvkey,
                     reason="Specify {GOERLI,GANACHE}_{SEED,XPRVKEY} to run MultiPayoutERC20 tests" )
@pytest.mark.parametrize( "testnet, provider, chain_id, src, src_prvkey, destination", web3_testers )
def test_multipayout_api( testnet, provider, chain_id, src, src_prvkey, destination ):
    """Create (or reuse) a network of MultiPayoutERC20 contracts to process a payment through to
    multiple recipients.

    We'll create a new client-unique <salt> and <data>, pre-compute a unique client payment address,
    issue an invoice, pay it and confirm that "Licensing" is satisfied by checking the associated
    <data> matches

    """
    if testnet != "Goerli":
        return
    # Get local Machine ID data.  Many software installations may be resident on the same machine
    # (and multiple virtual machines may have the same Machine ID; even though this isn't really
    # supposed to happen, we assume it does.)

    machine			= licensing.machine_UUIDv4( machine_id_path=__file__.replace( ".py", ".machine-id" ))
    print( f"{machine} == {machine.bytes.hex()}" )

    # Get unique Agent ID Keypair (plaintext; no username/password required)
    (keyname,keypair),		= licensing.load_keypairs(
        extra=[os.path.dirname( __file__ )], filename=__file__ )
    print( f"{licensing.into_b64( keypair.vk )}: {keyname}" )

    # OK, we can now sign the 128-bit UUIDv4 bytes w/ the agent keypair.sk (signing key).  The first
    # 64 bytes of the signed document is the signature.
    machine_signed		= ed25519.crypto_sign( machine.bytes, keypair.sk )
    print( f"{licensing.into_b64( keypair.vk )}: machine UUID sign:       {machine_signed.hex()}" )
    machine_sig			= machine_signed[:64]
    print( f"{licensing.into_b64( keypair.vk )}: machine UUID signature:  {licensing.into_b64( machine_sig )}" )
    assert ed25519.crypto_sign_open( machine_sig + machine.bytes, keypair.vk ) == machine.bytes, \
        f"Failed to verify machine ID {machine.bytes.hex()} w/ signature {licensing.into_b64( machine_sig )}"

    # A 512-bit Ed25519 signature encodes 2 points on an elliptical curve, but won't fit into our
    # 256-bit <data>, so hash it (along with the document).  The result is a "fingerprint" of the
    # signature + document, allowing a client to *confirm* that they arrived at the same signature
    # (must have the same signing key, and the same data).  Nobody will be able to use the <data>
    # directly to *verify* that the signature, however.  Therefore, future "Licensing" verification
    # confirms 2 facts about the client (assuming the client is running un-corrupted software):
    #
    # - It has the same Machine ID
    # - It has the Ed25519 signing key (not just the public key)
    salt			= keypair.vk
    data			= sha256( machine_signed ).digest()
    assert len( salt ) == len( data ) == 256//8
    print( f"{licensing.into_b64( keypair.vk )} salt: {salt.hex()}" )
    print( f"{licensing.into_b64( keypair.vk )} data: {data.hex()}" )

    # Now, we're ready to precompute this client's payment address.  We can ask the Contract for it,
    # or compute it ourselves (but we have to know the ...Forwarder contract creation bytecode
    # hash.)  This is a public immutable bytes32 value provided by the contract, which we can obtain
    # with a free .call.
    multipayout_address		= "0x8b3D24A120BB486c2B7583601E6c0cf37c9A2C04"

    # Since we're not deploying or making non-free Contract API calls, don't bother providing a
    # legitimate GasOracle, eg.Etherscan( chain=chain, speed=speed )
    mp_c			= MultiPayoutERC20(
        provider,
        address		= multipayout_address,
        agent		= src,
        agent_prvkey	= src_prvkey
    )
    assert mp_c.forwarder_address( 0 ) \
        == contract_address( address=multipayout_address, salt=0, creation_hash=mp_c._forwarder_hash ) \
        == mp_c._forwarder_address_precompute( 0 ) \
        == "0xb2D03aD9a84F0E10697BF2CDc2B98765688134d8"

    # Make certain we haven't cluttered up the namespace (covered up any contract method names)
    attrs_bare			= [n for n in dir( mp_c ) if not n.startswith( '_' )]
    assert not attrs_bare


@pytest.mark.parametrize( "testnet, provider, chain_id, src, src_prvkey, destination", web3_testers )
def test_multipayout_recover( testnet, provider, chain_id, src, src_prvkey, destination ):
    """Recover an existing MultiPayoutERC20
    """
    if testnet != "Goerli":
        return
    # Recover an already deployed MultiPayoutERC20.  No need for a GasOracle (free calls only)
    mp_r			= MultiPayoutERC20(
        provider,
        address		= "0xdb0bFb2E582Ecd3bc51C264d2F087D034857bF40",
    )
    print( f"Recovered MultiPayoutERC20 at {mp_r._address}: {mp_r}" )
    assert str(mp_r) == """\
MultiPayoutERC20 Payees:
    | Payee                                      | Share                 |   Frac. % |   Reserve |   Reserve/2^16 |   Frac.Rec. % |   Error % |
    |--------------------------------------------+-----------------------+-----------+-----------+----------------+---------------+-----------|
    | 0xEeC2b464c2f50706E3364f5893c659edC9E4153A | 14979/65536           |   22.8561 |     50557 |          50557 |       22.8561 |         0 |
    | 0xE5714055437154E812d451aF86239087E0829fA8 | 1228888999/4294967296 |   28.6123 |     41229 |          41229 |       28.6123 |         0 |
    | 0x7Fc431B8FC8250A992567E3D7Da20EE68C155109 | 2084414553/4294967296 |   48.5316 |         0 |              0 |       48.5316 |         0 |
ERC-20s:
    | Token                                      | Symbol   |   Digits |
    |--------------------------------------------+----------+----------|
    | 0xe802376580c10fE23F027e1E19Ed9D54d4C9311e | USDT     |        6 |
    | 0xde637d4C445cA2aae8F782FFAc8d2971b93A4998 | USDC     |        6 |
    | 0xaFF4481D10270F50f203E0763e2597776068CBc5 | WEENUS   |       18 |
    | 0x1f9061B953bBa0E36BF50F21876132DcF276fC6e | ZEENUS   |        0 |"""


@pytest.mark.skipif( not goerli_xprvkey and not ganache_xprvkey,
                     reason="Specify {GOERLI,GANACHE}_{SEED,XPRVKEY} to run MultiPayoutERC20 tests" )
@pytest.mark.parametrize( "testnet, provider, chain_id, src, src_prvkey, destination", web3_testers )
def test_multipayout_deploy( testnet, provider, chain_id, src, src_prvkey, destination ):
    """Deploy a new MultiPayoutERC20 w/ random Fractional share allocations from 1/1 to 1/999.

    Then, recover the contract just deployed.
    """
    if testnet != "Goerli":
        return
    # We'll use large "share" values, to ensure that we're likely to have fractions that don't
    # divide smoothly by a 1/2^bits divisor.
    payees			= {
        payee: Fraction( 1+random.choice( range( 100000 )))  # (1,99999)
        for payee in destination
    }
    erc20s 			= [ USDT_GOERLI, USDC_GOERLI, WEEN_GOERLI, ZEEN_GOERLI ]

    gas_oracle			= Etherscan( chain=Chain.Ethereum )

    mp_d			= MultiPayoutERC20(
        provider,
        agent		= src,
        agent_prvkey	= src_prvkey,
        payees		= payees,
        erc20s		= erc20s,
        gas_oracle	= gas_oracle,
        gas_oracle_timeout = 10,
    )
    print( f"Deployed  MultiPayoutERC20 to {mp_d._address}: \n{mp_d}" )

    # Recover the just-deployed MultiPayoutERC20.  Only free calls; no GasOracle needed
    mp_r			= MultiPayoutERC20(
        provider,
        address		= mp_d._address,
        agent		= src,
        agent_prvkey	= src_prvkey,
    )
    print( f"Recovered MultiPayoutERC20 at {mp_r._address}: \n{mp_r}" )

    # The deployed ._payees will not match the recovered _payees, because the original one has
    # full-precision shares/fractions, while the recovered one has fractions deduced from the
    # decimated "reserve" remainders stored in the contract.  However, the ._payees_reserve must be
    # identical.
    assert mp_r._payees_reserve == mp_d._payees_reserve
