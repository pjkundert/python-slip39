import json
import logging

import pytest

from .ethereum		import Etherscan, Chain, Speed

log				= logging.getLogger( 'ethereum_test' )


def test_ethereum_prices():
    ETH				= Etherscan( "Nothing" )  # Specify Nothing for Ethereum back-end (uses defualts)

    log.warning( "ETH: USD${}".format( ETH.ETH_USD ))
    log.warning( "Gas: USD${:7.2f} / 100,000 gas".format( 100000 * ETH.GAS_GWEI / ETH.ETH_GWEI * ETH.ETH_USD ))

    gas				= 21000
    spend			= 1.50
    gas_pricing			= ETH.maxPriorityFeePerGas( spend=spend, gas=gas )
    log.warning( f"{ETH.chain}: Gas Pricing EIP-1559 for max $1.50 per 21,000 Gas transaction: {json.dumps( gas_pricing )}" )
    assert gas_pricing['maxFeePerGas'] == pytest.approx( 71428571428.57143 )
    assert gas_pricing['maxPriorityFeePerGas'] == pytest.approx( 2000000000.0 )
    
    ETH.chain			= Chain.Ethereum

    gas_pricing			= ETH.maxPriorityFeePerGas( spend=1.50, gas=21000 )
    log.warning( f"{ETH.chain}: Gas Pricing EIP-1559 for max $1.50 per 21,000 Gas transaction: {json.dumps( gas_pricing )}" )
    assert gas_pricing['maxFeePerGas'] * gas / ETH.ETH_WEI * ETH.ETH_USD == pytest.approx( spend )
