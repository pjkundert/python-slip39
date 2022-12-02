import os
import json
import logging

from datetime		import datetime

import requests
from ..util		import memoize, retry
from ..defaults		import ETHERSCAN_MEMO_MAXAGE, ETHERSCAN_MEMO_MAXSIZE

# Get some basic Ethereum blockchain data used by tests

log				= logging.getLogger( 'ethereum' )

etherscan_urls			= dict(
    Ethereum	= 'https://api.etherscan.io/api',
    Goerli	= 'https://api-goerli.etherscan.io/api',
)


@memoize( maxage=ETHERSCAN_MEMO_MAXAGE, maxsize=ETHERSCAN_MEMO_MAXSIZE, log_at=logging.INFO )
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


@retry( tries=5, delay=3, backoff=1.5, log_at=logging.WARNING, exc_at=logging.WARNING, default_cls=dict ) 
def gasoracle( chain=None, **kwds ):
    """Return (possibly cached) Gas Oracle values from etherscan.io, or empty dict, allowing retries w/
    up to 3^5 seconds (4 min.) exponential backoff.

    """
    return etherscan(
        chain or 'Ethereum',
        (
            ('module', 'gastracker'),
            ('action', 'gasoracle'),
        ),
        **kwds,
    )

@retry( tries=5, delay=3, backoff=1.5, log_at=logging.WARNING, exc_at=logging.WARNING, default_cls=dict ) 
def ethprice( chain=None, **kwds ):
    """Return (possibly cached) Ethereum price from etherscan.io, or Exception"""
    return etherscan(
        chain or 'Ethereum',
        (
            ('module', 'stats'),
            ('action', 'ethprice'),
        ),
        **kwds,
    )


class Etherscan:
    """Retreive (or supply) some defaults for Ethereum pricing and some useful constants, IF you supply
    an etherscan.io API token in the ETHERSCAN_API_TOKEN environment variable.

    If Etherscan.UPDATED or .STATUS are falsey, this indicates that the value(s) are estimated;
    otherwise, they will return the approximate *nix timestamp of the provided Gas and Ethereum
    pricing, eg:

        >>> log.warning( f"Ethereum price: USD${Etherscan.ETH_USD:7.2f} ({Etherscan.STATUS or 'estimated'})" )

    """

    CHAIN			= "Ethereum"		# Or "Goerli"

    GWEI_WEI			= 10 ** 9		# GWEI, in WEIs
    ETH_GWEI			= 10 ** 9		# ETH, in GWEIs
    ETH_WEI			= 10 ** 18		# ETH, in WEIs

    @classmethod
    @property
    def LASTBLOCK( cls ):
        """Ethereum Gas Fee estimate comes from this block"""
        return int( gasoracle( chain=cls.CHAIN ).get( 'LastBlock', 0 ))

    @classmethod
    @property
    def GAS_GWEI( cls ):
        """Ethereum Gas Fee, in GWEI"""
        return float( gasoracle( chain=cls.CHAIN ).get( 'SafeGasPrice', 12.0 ))

    @classmethod
    @property
    def GAS_WEI( cls ):
        """Ethereum Gas Fee, in WEI"""
        return cls.GAS_GWEI * GWEI_WEI

    @classmethod
    @property
    def BASEFEE_GWEI( cls ):
        """Ethereum BaseFee, in GWEI"""
        return float( gasoracle( chain=cls.CHAIN ).get( 'suggestBaseFee', 10.0 ))

    @classmethod
    @property
    def BASEFEE_WEI( cls ):
        """Ethereum BaseFee, in WEI"""
        return cls.BASEFEE_GWEI * GWEI_WEI

    @classmethod
    @property
    def TIMESTAMP( cls ):
        return int( ethprice( chain=cls.CHAIN ).get( 'ethusd_timestamp', 0 ))

    @classmethod
    @property
    def ETH_USD( cls ):
        """ETH, in USD$"""
        return float( ethprice( chain=cls.CHAIN ).get( 'ethusd', 1000.00 ))

    @classmethod
    @property
    def UPDATED( cls ):
        return cls.LASTBLOCK and cls.TIMESTAMP

    @classmethod
    @property
    def STATUS( cls ):
        updated			= cls.UPDATED
        if updated:
            return datetime.utcfromtimestamp( updated ).ctime() + " UTC"
