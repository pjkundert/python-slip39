
import logging

from .ethereum		import Etherscan as ETH

log			= logging.getLogger( 'ethereum_test' )


def test_ethereum_prices():
    log.warning( "ETH: USD${}".format( ETH.ETH_USD ))
    log.warning( "Gas: USD${:7.2f} / 100,000 gas".format( 100000 * ETH.GAS_GWEI / ETH.ETH_GWEI * ETH.ETH_USD ))
