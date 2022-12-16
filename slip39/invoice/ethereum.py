import os
import json
import logging

from enum		import Enum
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


class Chain( Enum ):
    Nothing		= 0
    Ethereum		= 1
    Goerli		= 2


@memoize( maxage=ETHERSCAN_MEMO_MAXAGE, maxsize=ETHERSCAN_MEMO_MAXSIZE, log_at=logging.INFO )
def etherscan( chain, params, headers=None, apikey=None, timeout=None, verify=True ):
    """Queries etherscan.io, IFF you have an apikey.  Must specify name of Ethereum blockchain to use.
    The params must be a hashable sequence (tuple of tuples) usable to construct a dict, since
    memoize only caches based on args, and all args must be hashable.

    Raises exception on timeout, absence of successful response, absence of 'result' in response.
    Does no other checking on the content of the response' 'result'.

    """
    url				= etherscan_urls[chain.name]
    timeout			= timeout or 5.0
    headers			= headers or {
        'Content-Type':  'application/x-javascript',
    }
    params			= dict( params )
    params.setdefault( 'apikey', apikey or os.getenv( 'ETHERSCAN_API_TOKEN' ))  # May remain None

    if params.get( 'apikey' ):
        log.debug( "Querying {} w/ {}".format( url, params ))
        response		= requests.get(
            url,
            params	= params,
            headers	= headers,
            timeout	= timeout,
            verify	= verify,
        )
        assert response.status_code == 200, \
            "Failed to query {} for {}: {}".format( chain, params, response.text )
        log.info( "Querying {} w/ {}: {}".format(
            url, params,
            json.dumps( response.json(), indent=4 ) if log.isEnabledFor( logging.DEBUG ) else response.text
        ))
        return response.json()['result']  # A successful response must have a result

    return None


@retry( tries=5, delay=3, backoff=1.5, log_at=logging.WARNING, exc_at=logging.WARNING, default_cls=dict )
def gasoracle( chain=None, **kwds ):
    """Return (possibly cached) Gas Oracle values from etherscan.io, or empty dict, allowing retries w/
    up to 3^5 seconds (4 min.) exponential backoff.

    """
    return etherscan(
        chain or Chain.Ethereum,
        (
            ('module', 'gastracker'),
            ('action', 'gasoracle'),
        ),
        **kwds,
    )


@retry( tries=5, delay=3, backoff=1.5, log_at=logging.WARNING, exc_at=logging.WARNING, default_cls=dict )
def ethprice( chain=None, **kwds ):
    """Return (possibly cached) Ethereum price from etherscan.io, or empty dict (performs exponential
    backoff of 3^5 seconds (4 min.) on Exceptions.)

    """
    return etherscan(
        chain or Chain.Ethereum,
        (
            ('module', 'stats'),
            ('action', 'ethprice'),
        ),
        **kwds,
    )


class Speed( Enum ):
    Propose		= 0
    Safe		= 1
    Fast		= 2


class Etherscan:
    """Retrieve (or supply some defaults for) Gas and Ethereum pricing and some useful constants, IF
    you supply an etherscan.io API token in the ETHERSCAN_API_TOKEN environment variable and have
    network access.  Defaults to the Ethereum chain.

    If Etherscan.UPDATED or .STATUS are falsey, this indicates that the value(s) are estimated;
    otherwise, they will return the approximate *nix timestamp (or UTC time) of the provided Gas and
    Ethereum pricing, eg:

        >>> ETH = Etherscan( "Ethereum )
        >>> log.warning( f"Ethereum price: USD${ETH.ETH_USD:7.2f} ({ETH.STATUS or 'estimated'})" )


    To simplify Ethereum transaction gas pricing, we compute a proposed maxPriorityFeePerGas value;
    the only value required for new-style Ethereum transactions -- the "tip" we'll propose to
    influence our transaction to be included.  By default, we'll use the "ProposeGasPrice"
    (moderate tip).  Optionally, you may specify a Speed.Safe (slow, but should happen sometime
    soon) or Speed.Fast (should be prioritised and happen quickly).

    NOTE: Take care to ensure that any Wei values are integer; any larger denominatinos (eg. Gwei)
    should be able to handle fractional values.
    """
    def __init__( self, chain=None, speed=None ):
        if chain and isinstance( chain, str ):
            chain,		= ( c for c in Chain if c.name.lower() == chain.lower() )
        assert isinstance( chain, (Chain, type(None)) )
        self._chain		= chain or Chain.Ethereum

        if speed and isinstance( speed, str ):
            speed,		= ( s for s in Speed if s.name.lower() == speed.lower() )
        assert isinstance( speed, (Speed, type(None)) )
        self.speed		= speed or Speed.Propose

    GWEI_WEI			= 10 ** 9		# GWEI, in WEIs
    ETH_GWEI			= 10 ** 9		# ETH, in GWEIs
    ETH_WEI			= 10 ** 18		# ETH, in WEIs

    # Some defaults; maintain the invariant BASE_... + PRIORITY_... == GAS_...
    GAS_GWEI_DEFAULT		= 12.0
    BASE_GWEI_DEFAULT		= 10.0
    ETH_USD_DEFAULT		= 1000.0

    @classmethod
    def reset( cls ):
        """Clears all memoized data and retry back-offs, forcing a refresh on next call."""
        etherscan.reset()
        ethprice.reset()
        gasoracle.reset()

    @property
    def chain( self ):
        return self._chain
    @chain.setter
    def chain( self, chain ):
        """Change the chain, flushing any memoize/retry result caching."""
        self._chain		= chain
        self.reset()

    @property
    def GAS( self ):
        """Return Gas price oracle information, or empty dict"""
        return gasoracle( chain=self.chain )

    @property
    def ETH( self ):
        """Return Ethereum price information, or empty dict"""
        return ethprice( chain=self.chain )

    @property
    def LASTBLOCK( self ):
        """Ethereum Gas Fee estimate comes from this block"""
        return int( self.GAS.get( 'LastBlock', 0 ))

    @property
    def GAS_GWEI( self ):
        """Ethereum Gas Fee proposed, in GWEI.  This is the total Base + Priority fee to be paid, in Gwei
        per Gas, for the specified transaction Speed desired.  This would be the value you'd use for
        a traditional-style transaction with a "gasPrice" value.

        If we don't know, we'll just return a guess.  It is likely that you'll want to check if
        self.GAS (is empty) or self.LASTBLOCK (is falsey), and do something else to compute your gas
        pricing -- such as ask your Ethereum blockchain what it suggests, via the JSON
        eth_maxPriorityFeePerGas API call, for example.

        """
        return float( self.GAS.get( self.speed.name+'GasPrice', self.GAS_GWEI_DEFAULT ))

    @property
    def GAS_WEI( self ):
        """Ethereum Gas Fee, in WEI"""
        return int( self.GAS_GWEI * self.GWEI_WEI )

    @property
    def BASE_GWEI( self ):
        """Ethereum Base Fee estimate for upcoming block, in GWEI (Etherscan API returns fees in Gwei/Gas).

        """
        return float( self.GAS.get( 'suggestBaseFee', self.BASE_GWEI_DEFAULT ))

    @property
    def BASE_WEI( self ):
        """Ethereum Base Fee, in WEI"""
        return int( self.BASE_GWEI * self.GWEI_WEI )

    @property
    def PRIORITY_GWEI( self ):
        """Ethereum Priority Fee per Gas estimate for upcoming block, in GWEI.  Compute this by taking the
        Safe/Propose/Fast total Gas Price Fee estimate, and subtracting off the estimated Base Fee.

        This is what you'd supply if you want to use maxPriorityFeePerGas for your Ethereum
        transaction (actually, since they usually want it in Wei, use self.PRIORITY_WEI).

        """
        return self.GAS_GWEI - self.BASE_GWEI

    @property
    def PRIORITY_WEI( self ):
        return int( self.PRIORITY_GWEI * self.GWEI_WEI )

    @property
    def TIMESTAMP( self ):
        return int( self.ETH.get( 'ethusd_timestamp', 0 ))

    @property
    def ETH_USD( self ):
        """ETH, in USD$"""
        return float( self.ETH.get( 'ethusd', self.ETH_USD_DEFAULT ))

    @property
    def GAS_USD( self ):
        """Computes the cost per Gas, in USD$.  Use this to calculate a maxFeePerGas value, if you want to
        limit the cost for a transaction to some dollar amount (for the gas limit you've specified
        for the transaction).  If it turns out that the required transaction gas fees exceed the
        maxFeePerGas you've specified, the transaction will be rejected (and won't spend your gas!)

        For example, lets say you have a transaction you know will spend (less than) 100,000 gas so
        you specify a 'gas' limit of 100000.  But, you can wait, so you don't want to spend too much
        on the transaction, say less than USD$1.50.

            >>> gas, spend = 100000, 1.50  # USD$
            >>> ETH = Etherscan( "Ethereum )
            >>> maxFeePerGas = spend / ETH.GAS_USD ETH.GAS_WEI

        """
        return self.ETH_USD * self.GAS_GWEI / self.ETH_GWEI


    @property
    def UPDATED( self ):
        """If we successfully obtained Gas and Ethereum pricing, return the timestamp of the Ethereum."""
        return self.LASTBLOCK and self.TIMESTAMP

    @property
    def STATUS( self ):
        updated			= self.UPDATED
        if updated:
            return datetime.utcfromtimestamp( updated ).ctime() + " UTC"

    def maxFeePerGas( self, spend=None, gas=21000 ):
        """Returns new-style EIP-1559 gas fees, in Wei.  Computes a maxFeePerGas we're willing to pay, for
        max 'gas' (default: a standard ETH transfer), to keep total transaction cost below 'spend'.

        If incomputable (either spend or gas unspecified), returns the empty dict (no maxFeePerGas).

        """
        if not spend or not gas:
            return dict()
        assert isinstance( spend, (int,float,type(None))), \
            f"Require a numeric spend amount in USD$, not {spend!r}"
        assert isinstance( gas, (int,float,type(None))), \
            f"Require a numeric gas amount, not {gas!r}"

        # Eg. USD$1.50 * 10^9 / USD$1,000 == 1,500,000 Gwei to use on Gas
        gwei_available			= spend
        gwei_available		       *= self.ETH_GWEI
        gwei_available		       /= self.ETH_USD
        # 1.5e6 Gwei / 21,000 Gas == 71.4 Gwei/Gas max gas fee allowance
        gwei_per_gas			= gwei_available / gas
        wei_per_gas			= int( gwei_per_gas * self.GWEI_WEI )
        return dict(
            maxFeePerGas		= wei_per_gas
        )

    def maxPriorityFeePerGas( self, spend=None, gas=None ):
        """Returns new-style EIP-1559 gas Priority fee we'll likely need to pay, in Wei, to achieve the
        desired Speed (Safe, Propose or Fast).  This Priority Fee (plus the current network Base
        Fee) will be the Gas cost we'll pay, in Wei/Gas.

        If spend and gas is supplied, also includes the maxFeePerGas we're willing to spend.
        """
        gas_price			= dict(
            maxPriorityFeePerGas	= self.PRIORITY_WEI,
        ) | self.maxFeePerGas( spend=spend, gas=gas )
        log.info(
            f"{self.chain}: EIP-1559 Gas Pricing at USD${self.ETH_USD:8,.2f}/ETH: : {gas_price['maxPriorityFeePerGas'] / self.GWEI_WEI:9,.2f} Priority + {self.BASE_GWEI:9,.2f} Base Gwei/Gas"
            + ( f"; for max USD${spend:9,.2f} per {gas:10,} Gas transaction: {gas_price['maxFeePerGas'] / self.GWEI_WEI:9,.2f} Gwei/Gas" if 'maxFeePerGas' in gas_price else "" )
        )
        return gas_price

    def gasPrice( self ):
        """The traditional gasPrice interface.  Returns the total gasPrice we're willing to pay, estimated based on
        the latest block. """
        gas_price			= dict(
            gasPrice			= self.GAS_WEI,
        )
        log.info(
            f"{self.chain}: Traditional Gas Pricing: {gas_price['gasPrice'] / self.GWEI_WEI:9,.2f} Gwei/Gas"
        )
        return gas_price
