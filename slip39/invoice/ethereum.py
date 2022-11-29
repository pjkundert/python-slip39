import os
import json
import logging

import requests
from ..util		import memoize
from ..defaults		import ETHERSCAN_MEMO_MAXAGE, ETHERSCAN_MEMO_MAXSIZE

# Get some basic Ethereum blockchain data used by tests

log				= logging.getLogger( 'ethereum' )

etherscan_urls			= dict(
    Ethereum	= 'https://api.etherscan.io/api',
    Goerli	= 'https://api-goerli.etherscan.io/api',
)


@memoize( maxage=ETHERSCAN_MEMO_MAXAGE, maxsize=ETHERSCAN_MEMO_MAXSIZE )
def etherscan( chain, params, headers=None, apikey=None, timeout=None, verify=True ):
    """Queries etherscan.io, IFF you have an apikey.  Must specify name of Ethereum blockchain to use.
    The params must be a hashable sequence (tuple of tuples) usable to construct a dict, since
    memoize only caches based on args, and all args must be hashable.

    """
    url				= etherscan_urls[chain]
    timeout			= timeout or 5.0
    headers			= headers or {
        'Content-Type':  'application/x-javascript',
    }
    params			= dict( params )
    params.setdefault( 'apikey', apikey or os.getenv( 'ETHERSCAN_API_TOKEN' ))  # May remain None

    result			= None
    if params.get( 'apikey' ):
        log.debug( "Querying {} w/ {}".format( url, params ))
        response		= requests.get(
            url,
            params	= params,
            headers	= headers,
            timeout	= timeout,
            verify	= verify,
        )
        if response.status_code == 200:
            log.info( "Querying {} w/ {}: {}".format(
                url, params,
                json.dumps( response.json(), indent=4 ) if log.isEnabledFor( logging.DEBUG ) else response.text
            ))
            result		= response.json()['result']  # A successful response must have a result 
        else:
            log.warning( "Failed to query {} for {}: {}".format( chain, params, response.text ))
    return result


def gasoracle( chain=None, **kwds ):
    """Return (possibly cached) Gas Oracle values from etherscan.io."""
    return etherscan(
        chain or 'Ethereum',
        (
            ('module', 'gastracker'),
            ('action', 'gasoracle'),
        ),
        **kwds,
    )


def ethprice( chain=None, **kwds ):
    """Return (possibly cached) Ethereum price from etherscan.io."""
    return etherscan(
        chain or 'Ethereum',
        (
            ('module', 'stats'),
            ('action', 'ethprice'),
        ),
        **kwds,
    )


# 
# Retreive (or supply) some defaults for Ethereum pricing and some useful constants
# 
#     If GWEI_GAS_BLOCK or ETH_USE_TIMESTAMP are None, this indicates that
# the value was estimated.
# 
try:
    gasprices			= gasoracle()
    GWEI_GAS_BLOCK		= int( gasprices['LastBlock'] )
    GWEI_GAS			= float( gasprices['SafeGasPrice'] )
    GWEI_BASEFEE		= float( gasprices['suggestBaseFee'] )
except Exception as exc:
    log.warning( f"Couldn't obtain current Gas Prices: {exc}; defaulting..." )
    GWEI_GAS_BLOCK		= None
    GWEI_GAS			= 12.0
    GWEI_BASEFEE		= 10.0

try:
    ethprices			= ethprice()
    ETH_USD_TIMESTAMP		= int( ethprices['ethusd_timestamp'] )
    ETH_USD			= float( ethprices['ethusd'] )
except Exception as exc:
    log.warning( f"Couldn't obtain current Ethereum Price: {exc}; defaulting..." )
    ETH_USD_TIMESTAMP		= None
    ETH_USD			= 1000.00  # order of magnitude ~2022/10/25


WEI_GWEI			= 10 ** 9
GWEI_ETH			= 10 ** 9
WEI_ETH				= 10 ** 18

WEI_GAS				= int( WEI_GWEI * GWEI_GAS )
WEI_BASEFEE			= int( WEI_GWEI * GWEI_BASEFEE )
