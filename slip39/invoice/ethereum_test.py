
import logging

from .ethereum		import *

log			= logging.getLogger( 'ethereum_test' )


def test_ethereum_prices():
    log.warning( "ETH: USD${}".format( ETH_USD ))
    log.warning( "Gas: USD${:7.2f} / 100,000 gas".format( 100000 * GWEI_GAS / GWEI_ETH * ETH_USD ))
