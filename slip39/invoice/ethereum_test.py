import json
import logging
import os
import time

import pytest

from ..util		import timer, ordinal

from .ethereum		import Etherscan, Chain, gasoracle

log				= logging.getLogger( 'ethereum_test' )


def test_ethereum_prices():
    """Check that defaults for ETH pricing work, and that obtaining data from https://etherscan.io works
    even without an ETHERSCAN_API_TOKEN (subject to default 1/5s rate limit.

    """
    ETH				= Etherscan( "Nothing" )  # Specify Nothing for Ethereum back-end (uses defualts)

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
