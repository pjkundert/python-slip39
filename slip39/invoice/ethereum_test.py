import json
import logging
import os
import time

import pytest

from web3		import Web3		# noqa F401

from ..util		import timer, ordinal
from .ethereum		import Etherscan, Chain, gasoracle, alchemy_url, tokenprices, tokenratio

log				= logging.getLogger( 'ethereum_test' )


def test_etherscan_ethprice():
    """Check that defaults for ETH pricing work, and that obtaining data from https://etherscan.io works
    even without an ETHERSCAN_API_TOKEN (subject to default 1/5s rate limit.

    """
    ETH				= Etherscan( 'Nothing' )  # Specify Nothing for Ethereum back-end (uses defaults)

    log.warning( "ETH: USD${}".format( ETH.ETH_USD ))
    log.warning( "Gas: USD${:7.2f} / 100,000 gas".format( 100000 * ETH.GAS_GWEI / ETH.ETH_GWEI * ETH.ETH_USD ))

    gas				= 21000
    spend			= 1.50
    gas_pricing			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas )
    log.warning( f"{ETH.chain}: Gas Pricing EIP-1559 for max $1.50 per 21,000 Gas transaction: {json.dumps( gas_pricing )}" )
    assert gas_pricing['maxFeePerGas'] == pytest.approx( 71428571428.57143 )
    assert gas_pricing['maxPriorityFeePerGas'] == pytest.approx( 2000000000.0 )

    # Now try the real Etherscan API.  Will fail if we don't have network access to
    # https://etherscan.io.  If we don't have an API token, observe that the rate limit is applied.
    # Otherwise, if we do have an API token, warn if we observe a rate limit, or fail to get data.
    ETH.chain			= Chain.Ethereum
    if ETH.ETH_USD == ETH.ETH_USD_DEFAULT or not ETH.TIMESTAMP:
        log.warning( f"Should have successfully obtained Ethereum price from Etherscan, regardless of ETHERSCAN_API_TOKEN: {os.getenv( 'ETHERSCAN_API_TOKEN' )}" )
        return
    # We've successfully reached Etherscan once!  Should eventually succeed again.
    beg				= timer()
    while timer() - beg < 10 and not ETH.UPDATED:  # will loop 'til time exhausted or retry succeeeds
        gas_pricing		= ETH.maxPriorityFeePerGas( spend=1.50, gas=21000 )
        now			= timer()
        log.warning( f"{ETH.chain}: After {now - beg:.2f}s ({now-gasoracle.lst:.2f}s since last try): Gas Pricing EIP-1559 for max $1.50 per 21,000 Gas transaction: {json.dumps( gas_pricing )}" )
        if ETH.UPDATED:  # Ignore, if we don't have communications w/ the Ethereum chain data source
            assert gas_pricing['maxFeePerGas'] * gas / ETH.ETH_WEI * ETH.ETH_USD == pytest.approx( spend )
        time.sleep( 1 )
    now				= timer()
    assert ETH.UPDATED, \
        f"Failed to obtain Gas Oracle after {now-gasoracle.lst:.2f}s since {ordinal(gasoracle.cnt)} try"


def test_1inch_offchainoracle():
    """Consult the 1inch offChainOracle contract to query several continuous liquidity pools for Crypto prices.

    """

    # Connect to the real Ethereum blockchain
    w3				= Web3( Web3.WebsocketProvider( alchemy_url( Chain.Ethereum )))

    # See: https://github.com/1inch/spot-price-aggregator/blob/master/examples/multiple-prices.js
    # multicall_abi		= [{"inputs":[{"components":[{"internalType":"address","name":"to","type":"address"},{"internalType":"bytes","name":"data","type":"bytes"}],"internalType":"struct MultiCall.Call[]","name":"calls","type":"tuple[]"}],"name":"multicall","outputs":[{"internalType":"bytes[]","name":"results","type":"bytes[]"},{"internalType":"bool[]","name":"success","type":"bool[]"}],"stateMutability":"view","type":"function"}]  # noqa: E501
    # multicall_contract		= w3.eth.contract( multicall_abi, '0x07D91f5fb9Bf7798734C3f606dB065549F6893bb' )

    offchainoracle_abi		= [{"inputs":[{"internalType":"contract MultiWrapper","name":"_multiWrapper","type":"address"},{"internalType":"contract IOracle[]","name":"existingOracles","type":"address[]"},{"internalType":"enum OffchainOracle.OracleType[]","name":"oracleTypes","type":"uint8[]"},{"internalType":"contract IERC20[]","name":"existingConnectors","type":"address[]"},{"internalType":"contract IERC20","name":"wBase","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract IERC20","name":"connector","type":"address"}],"name":"ConnectorAdded","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract IERC20","name":"connector","type":"address"}],"name":"ConnectorRemoved","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract MultiWrapper","name":"multiWrapper","type":"address"}],"name":"MultiWrapperUpdated","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract IOracle","name":"oracle","type":"address"},{"indexed":False,"internalType":"enum OffchainOracle.OracleType","name":"oracleType","type":"uint8"}],"name":"OracleAdded","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract IOracle","name":"oracle","type":"address"},{"indexed":False,"internalType":"enum OffchainOracle.OracleType","name":"oracleType","type":"uint8"}],"name":"OracleRemoved","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"previousOwner","type":"address"},{"indexed":True,"internalType":"address","name":"newOwner","type":"address"}],"name":"OwnershipTransferred","type":"event"},{"inputs":[{"internalType":"contract IERC20","name":"connector","type":"address"}],"name":"addConnector","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IOracle","name":"oracle","type":"address"},{"internalType":"enum OffchainOracle.OracleType","name":"oracleKind","type":"uint8"}],"name":"addOracle","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"connectors","outputs":[{"internalType":"contract IERC20[]","name":"allConnectors","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"srcToken","type":"address"},{"internalType":"contract IERC20","name":"dstToken","type":"address"},{"internalType":"bool","name":"useWrappers","type":"bool"}],"name":"getRate","outputs":[{"internalType":"uint256","name":"weightedRate","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"srcToken","type":"address"},{"internalType":"bool","name":"useSrcWrappers","type":"bool"}],"name":"getRateToEth","outputs":[{"internalType":"uint256","name":"weightedRate","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"multiWrapper","outputs":[{"internalType":"contract MultiWrapper","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"oracles","outputs":[{"internalType":"contract IOracle[]","name":"allOracles","type":"address[]"},{"internalType":"enum OffchainOracle.OracleType[]","name":"oracleTypes","type":"uint8[]"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"connector","type":"address"}],"name":"removeConnector","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IOracle","name":"oracle","type":"address"},{"internalType":"enum OffchainOracle.OracleType","name":"oracleKind","type":"uint8"}],"name":"removeOracle","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"renounceOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract MultiWrapper","name":"_multiWrapper","type":"address"}],"name":"setMultiWrapper","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"newOwner","type":"address"}],"name":"transferOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"}]  # noqa: E501

    offchainoracle_contract	= w3.eth.contract( address='0x07D91f5fb9Bf7798734C3f606dB065549F6893bb',  abi=offchainoracle_abi)

    token			= dict(
        address		= '0xdAC17F958D2ee523a2206206994597C13D831ec7',
        decimals	= 6,
    )

    token_price			= offchainoracle_contract.functions.getRateToEth( token['address'], True ).call()
    log.info( f"ETH/USDT: {token_price}" )

    eth_usdt			= token_price / (10 ** ( 18 + 18 - token['decimals'] ))
    log.info( f"ETH/USDT: {eth_usdt}" )
    log.info( f"USDT/ETH: {1/eth_usdt}" )


HOT			= "0x6c6EE5e31d828De241282B9606C8e98Ea48526E2"
USDT			= "0xdAC17F958D2ee523a2206206994597C13D831ec7"
USDC			= "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
WBTC			= "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599"
WETH			= "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


def test_tokenprice():
    """Get prices vs. the default base (ETH), and a low-value token.  Should retain precision,
    due to underlying 10^18 fixed-point offset."""
    for base in (None, HOT):
        prices_eth			= list( tokenprices( USDC, USDT, WBTC, WETH, base=base ))
        log.info( "Token prices: " + json.dumps( prices_eth, indent=4, default=str ))

        for t,b,f in prices_eth:
            log.info( f"{t.symbol:>6}/{b.symbol:<6}: {float( f ):13.4f} =~= {str(f)}" )

        # WETH in terms of ETH should be close to 1.0 (ignore for any other base currency)
        assert base is not None or float( prices_eth[-1][2] ) == pytest.approx( 1.0 ), \
            "WETH/ETH is diverging from unity"

        # WBTC, WETH vs. ETH should be multiples of USDC vs. ETH
        assert float( prices_eth[-1][2] ) / float( prices_eth[0][2] ) > 1000, \
            "WETH/USDC is inverted?"
        assert float( prices_eth[-2][2] ) / float( prices_eth[0][2] ) > 100, \
            "WBTC/USDC is inverted?"


def test_tokenratio():
    # Now, get the token price ratio of two tokens (both cached, relative to default ETH)
    WBTC_USDC		= tokenratio( WBTC, USDC )
    log.info( f"{WBTC_USDC[0].symbol:>6}/{WBTC_USDC[1].symbol:<6}: {float( WBTC_USDC[2] ):13.4f} =~= {WBTC_USDC[2]}" )
    assert WBTC_USDC[2] > 10000, \
        "WBTC has crashed vs. USDC?"

    HOT_USDC		= tokenratio( "HOT", "USDC" )
    log.info( f"{HOT_USDC[0].symbol:>6}/{HOT_USDC[1].symbol:<6}: {float( HOT_USDC[2] ):13.4f} =~= {HOT_USDC[2]}" )
    assert HOT_USDC[2] < .10, \
        "HOT has exploded vs. USDC?"
