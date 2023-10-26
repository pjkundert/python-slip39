
#
# Python-slip39 -- Ethereum SLIP-39 Account Generation and Recovery
#
# Copyright (c) 2022, Dominion Research & Development Corp.
#
# Python-slip39 is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is also available under alternative (eg. Commercial) licenses, at
# your option.  See the LICENSE file at the top of the source tree.
#
# Python-slip39 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#

from __future__		import annotations

import json
import logging
import os
import traceback
import time

from dataclasses	import dataclass
from datetime		import datetime
from enum		import Enum
from fractions		import Fraction
from hashlib		import sha256
from pathlib		import Path
from typing		import Dict, Optional, Union, Tuple

import requests
import eth_account
import eth_abi
import solcx

from rlp		import encode as rlp_encode
from web3		import Web3
from web3.middleware	import construct_sign_and_send_raw_middleware

from ..api		import Account
from ..util		import memoize, retry, commas, into_bytes, timer
from ..defaults		import (
    ETHERSCAN_MEMO_MAXAGE, ETHERSCAN_MEMO_MAXSIZE,
    TOKPRICES_MEMO_MAXAGE, TOKPRICES_MEMO_MAXSIZE,
    INVOICE_PROXIES,
)


__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( 'ethereum' )


def contract_address(
    address,			# Address that is constructing the contract
    salt		= None,
    creation		= None,
    creation_hash	= None,
    nonce		= None,		# traditional CREATE used address/nonce
):
    """Deduces the Contract Address that will result from a creator's 'address' and a
    transaction/CREATE (given a 'nonce'), or CREATE2 (given a 'salt' and the contract's 'creation'
    bytecode).

    """
    b_address			= into_bytes( address )
    assert isinstance( b_address, bytes ) and len( b_address ) == 20, \
        f"Expected 20-byte adddress, got {b_address!r}"

    if nonce is not None and salt is None and creation is None and creation_hash is None:
        # A CREATE (traditional, or transaction-based) contract creation; only address and nonce
        assert isinstance( nonce, int ), \
            f"The nonce for CREATE must be an integer, not {nonce!r}"
        b_result		= Web3.keccak( rlp_encode([ b_address, nonce ]) )
    else:
        # A CREATE2 (deterministic) contract creation
        assert salt is not None and ( creation is not None or creation_hash is not None ) and nonce is None, \
            "Need salt and creation bytecode/hash for CREATE2"
        b_pre			= into_bytes( '0xff' )
        if isinstance( salt, int ):
            b_salt		= eth_abi.encode( [ 'uint256' ], [ salt ] )
        else:
            b_salt		= into_bytes( salt )
        assert len( b_salt ) == 32, \
            f"Expected 32-byte salt, got {len(b_salt)} bytes"
        if creation_hash:
            b_creation_hash	= into_bytes( creation_hash )
        else:
            b_creation_hash	= Web3.keccak( into_bytes( creation ))
        b_result		= Web3.keccak( b_pre + b_address + b_salt + b_creation_hash )

    result_address		= Web3.to_checksum_address( b_result[12:].hex() )

    return result_address


class Chain( Enum ):
    Nothing		= 0
    Ethereum		= 1
    Goerli		= 2


#
# Etherscan API, for accessing Gas Oracle and wallet data
#
etherscan_urls			= dict(
    Ethereum	= 'https://api.etherscan.io/api',
    Goerli	= 'https://api-goerli.etherscan.io/api',
)

#
# Alchemy API, for accessing the Ethereum blockchain w/o running a local instance
#
#     They provide a free "testing" API token, with a very low 50 "Compute Units/Second" limit, for
# testing their API: https://docs.alchemy.com/reference/throughput.  This should be sufficient for
# accessing "free" (view) APIs in contracts.  However, for any advanced usage (ie. to deploy
# contracts), you'll probably need an official ALCHEMY_API_TOKEN
#
alchemy_urls			= dict(
    Ethereum	= 'eth-mainnet.g.alchemy.com/v2',
    Goerli	= 'eth-goerli.g.alchemy.com/v2',
)

alchemy_api_testing		= dict(
    Goerli	= 'AxnmGEYn7VDkC4KqfNSFbSW9pHFR7PDO',
    Ethereum	= 'J038e3gaccJC6Ue0BrvmpjzxsdfGly9n',
)


def alchemy_url( chain, protocol='wss' ):
    """Return our Alchemy API URL, including our API token, from the ALCHEMY_API_TOKEN environment
    variable.

    If none specified, we'll default to their "Testing" API token, which should be adequate for
    low-rate "free" (view) contract APIs.  However, for deploying contracts, either an official
    (free) Alchemy API token will be required, or a local Ethereum node.

    """
    assert protocol in ( 'wss', 'https' ), \
        "Must specify either Websocket over SSL ('wss') or HTTP over SSL ('https')"
    api_token			= os.getenv( 'ALCHEMY_API_TOKEN' )
    if not alchemy_url.api_token or api_token != alchemy_url.api_token:
        # Alchemy API token not yet discovered, or has changed
        if api_token:
            alchemy_url.api_token	= api_token
            log.info( f"Using supplied Alchemy {chain} API token: {alchemy_url.api_token:.5}..." )
        elif not alchemy_url.api_token:
            alchemy_url.api_token	= alchemy_api_testing[chain.name]
            log.warning( f"Using \"Testing\" Alchemy {chain} API token: {alchemy_url.api_token};"
                         " obtain an official API key: https://docs.alchemy.com/reference/api-overview" )
    return f"{protocol}://{alchemy_urls[chain.name]}/{alchemy_url.api_token}"
alchemy_url.api_token		= None   # noqa E305


@memoize( maxage=ETHERSCAN_MEMO_MAXAGE, maxsize=ETHERSCAN_MEMO_MAXSIZE, log_at=logging.INFO )
def etherscan( chain, params, headers=None, apikey=None, timeout=None, verify=True ):
    """Queries etherscan.io, optionally w/ your apikey.  Must specify name of Ethereum blockchain to
    use.  The params must be a hashable sequence (tuple of tuples) usable to construct a dict, since
    memoize only caches based on args, and all args must be hashable.

    Raises exception on timeout, absence of successful response, absence of 'result' in response.
    Does no other checking on the content of the response' 'result'.

    Without an API key, request rates are severely restricted to ~1/5s, eg.:
        {
            "status": "1",
            "message": "OK-Missing/Invalid API Key, rate limit of 1/5sec applied",
            "result": {
                "ethbtc": "0.07217",
                "ethbtc_timestamp": "1671982262",
                "ethusd": "1214.6",
                "ethusd_timestamp": "1671982258"
            }
        }

    or:

        {
            "status": "0",
            "message": "NOTOK",
            "result": "Max rate limit reached, please use API Key for higher rate limit"
        }


    """
    assert chain.name in etherscan_urls, \
        f"No API service URL specified for {chain}"
    url				= etherscan_urls[chain.name]
    timeout			= timeout or 5.0
    headers			= headers or {
        'Content-Type':  'application/x-javascript',
    }
    params			= dict( params )
    if apikey is None:
        apikey			= os.getenv( 'ETHERSCAN_API_TOKEN' )
    if apikey and apikey.strip():  # May remain None, or be empty
        params.setdefault( 'apikey', apikey.strip() )

    # A successful request is a 200 OK, with a JSON-encoded result dict/ w a status: "1".  We do not
    # want to return any non-Exception response excepts successes, because these are Memoized.
    log.debug( "Querying {} w/ {}".format( url, params ))
    try:
        response		= requests.get(
            url,
            params	= params,
            headers	= headers,
            timeout	= timeout,
            verify	= verify,
        )
        assert response.status_code == 200, \
            "Failed to query {} for {}: {}".format( chain, params, response.text )
        response_json	= response.json()
        assert hasattr( response_json, 'keys' ) and {'status', 'result'} <= set( response_json.keys() ) and int( response_json['status'] ), \
            "Query {} for {} yielded invalid response: {}".format( chain, params, response.text )
    except Exception as exc:
        log.info( f"Query failed w/ Exception: {exc}" )
        raise

    # OK, got a valid, successful response we are prepared to Memoize!
    log.info( "Querying {} w/ {}: {}".format(
        url, params,
        json.dumps( response_json, indent=4 ) if log.isEnabledFor( logging.DEBUG ) else response.text
    ))
    return response_json['result']


@retry( tries=5, delay=3, backoff=1.5, log_at=logging.INFO, exc_at=logging.WARNING, default_cls=dict )
def gasoracle( chain=None, **kwds ):
    """Return (possibly cached) Gas Oracle values from etherscan.io, or empty dict, allowing retries w/
    up to 3*1.5^5 seconds (22s) exponential backoff.

    """
    return etherscan(
        chain or Chain.Ethereum,
        (
            ('module', 'gastracker'),
            ('action', 'gasoracle'),
        ),
        **kwds,
    )


@retry( tries=5, delay=3, backoff=1.5, log_at=logging.INFO, exc_at=logging.WARNING, default_cls=dict )
def ethprice( chain=None, **kwds ):
    """Return (possibly cached) Ethereum price in $USD from etherscan.io, or empty dict (performs exponential
    backoff of 3*1.5^5 seconds (22s) on Exceptions.)

    """
    return etherscan(
        chain or Chain.Ethereum,
        (
            ('module', 'stats'),
            ('action', 'ethprice'),
        ),
        **kwds,
    )


@retry( tries=5, delay=3, backoff=1.5, log_at=logging.INFO, exc_at=logging.WARNING, default_cls=dict )
def erc20tx( chain=None, address=None, token=None, **kwds ):
    """Return (possibly cached) ERC-20 transactions from etherscan.io, or empty dict (performs exponential
    backoff of 3*1.5^5 seconds (22s) on Exceptions.)

    Caches based on account address and (optionally) a specific token address.  Otherwise, returns
    all (known) ERC-20 token operations on the specified account.

    TODO: There may be unknown ERC-20 tokens that this won't find, unless contractAddress specified.

    """
    assert address is not None, \
        "Require an Ethereum account 'address' to query for ERC-20 transactions"
    if token is None:
        params			= (
            ('module', 'account'),
            ('action', 'tokentx'),
            ('address', address),
        )
    else:
        params			= (
            ('module', 'account'),
            ('action', 'tokentx'),
            ('address', address),
            ('contractAddress', token),
        )
    return etherscan(
        chain or Chain.Ethereum,
        params,
        **kwds,
    )


@retry( tries=5, delay=3, backoff=1.5, log_at=logging.INFO, exc_at=logging.WARNING, default_cls=dict )
def etherbalance( chain=None, address=None, **kwds ):
    """Return (possibly cached) ETH balance from etherscan.io, or empty dict (performs exponential
    backoff of 3^5 seconds (4 min.) on Exceptions.)

    Caches based on account address.

    """
    assert address is not None, \
        "Require an Ethereum account 'address' to query for Ethereum balance"
    params			= (
        ('module', 'account'),
        ('action', 'balance'),
        ('address', address),
    )
    return etherscan(
        chain or Chain.Ethereum,
        params,
        **kwds,
    )


@retry( tries=5, delay=3, backoff=1.5, log_at=logging.INFO, exc_at=logging.WARNING, default_cls=dict )
def ethertx( chain=None, address=None, **kwds ):
    """Return (possibly cached) ETH normal transactions from etherscan.io, or empty dict (performs exponential
    backoff of 3^5 seconds (4 min.) on Exceptions.)

    Caches based on account address.

    Includes contract invocations, incoming/outgoing value transactions, etc., including those that
    have "isError": "1".

    """
    assert address is not None, \
        "Require an Ethereum account 'address' to query for Ethereum transactions"
    params			= (
        ('module', 'account'),
        ('action', 'txlist'),
        ('address', address),
    )
    return etherscan(
        chain or Chain.Ethereum,
        params,
        **kwds,
    )


class Direction( Enum ):
    Incoming		= 0b01
    Outgoing		= 0b10
    Both		= 0b11


def etherio( chain=None, address=None, direction=None, **kwds ):
    """Yields a sequence of successful Ethereum value incoming/outgoing transactions for an account.
    By default, returns only Incoming value transactions.

    Ignores non-value (eg. contract) and failed transactions.

    """
    if direction is None:
        direction		= Direction.Incoming
    for tx in ethertx( chain=chain, address=address, **kwds ):
        if tx["value"] == "0" or tx["isError"] != "0":
            continue
        # A non-error value-bearing transaction.  Ignore?
        if not ( direction == Direction.Both
                 or (( direction.value & Direction.Incoming.value ) and tx["to"  ].lower() == address.lower() )
                 or (( direction.value & Direction.Outgoing.value ) and tx["from"].lower() == address.lower() )):
            continue
        yield tx


def erc20io( chain=None, address=None, token=None, tokens=None, direction=None, **kwds ):
    """Yields a sequence of successful ERC-20 value incoming/outgoing transactions for an account.
    By default, returns only Incoming value transactions.

    Specifying a specific 'token' limits the query to only a single token.  Alternatively,
    specifying a set/list of tokens filters transactions to only those tokens.

    """
    assert not bool( token ) or not bool( tokens ) or token in tokens, \
        "Cannot specify both a 'token' and 'tokens' set that do not overlap"
    if direction is None:
        direction		= Direction.Incoming
    tokens			= set( t.lower() for t in tokens ) if tokens else set()
    for tx in erc20tx( chain=chain, address=address, token=token ):
        if tokens and tx["contractAddress"].lower() not in tokens:
            continue
        if not ( direction == Direction.Both
                 or (( direction.value & Direction.Incoming.value ) and tx["to"  ].lower() == address.lower() )
                 or (( direction.value & Direction.Outgoing.value ) and tx["from"].lower() == address.lower() )):
            continue
        yield tx


class Speed( Enum ):
    Propose		= 0
    Safe		= 1
    Fast		= 2


class GasOracle:
    GWEI_WEI			= 10 ** 9		# GWEI, in WEIs
    ETH_GWEI			= 10 ** 9		# ETH, in GWEIs
    ETH_WEI			= 10 ** 18		# ETH, in WEIs

    # Some defaults; maintain the invariant BASE_... + PRIORITY_... == GAS_...
    GAS_GWEI_DEFAULT		= 12.0
    BASEFEE_GWEI_DEFAULT	= 10.0
    ETH_USD_DEFAULT		= 1000.0

    @property
    def ETH_USD( self ):
        """Return some estimate of ETH value in USD$, for use in Gas Price calculations."""
        return self.ETH_USD_DEFAULT

    def __bool__( self ):
        """Return falsey until this GasOracle is available.  Good for waiting for Gas Oracle sources
        with API rate limits, etc, or just to use this as a default that is never ready.

        """
        return False

    def maxPriorityFeePerGas( self, spend=None, gas=None, max_factor=None ):
        """At the very least, computes EIP-1559 Gas pricing, in Wei.  If spend/gas supplied, should
        also include maxFeePerGas we're willing to spend for this transaction.

        """
        raise NotImplementedError()


class Etherscan( GasOracle ):
    """Retrieve (or supply some defaults for) Gas and Ethereum pricing and some useful constants, IF
    you supply an etherscan.io API token in the ETHERSCAN_API_TOKEN environment variable and have
    network access.  Defaults to the Ethereum chain.  Implements the GasOracle API.

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
    def ETH( self ):
        """Return Ethereum price information, or empty dict"""
        return ethprice( chain=self.chain )

    @property
    def TIMESTAMP( self ):
        """Indicates if the Ethereum price self.ETH has been queried."""
        return int( self.ETH.get( 'ethusd_timestamp', 0 ))

    @property
    def ETH_USD( self ):
        """ETH, in USD$"""
        return float( self.ETH.get( 'ethusd', self.ETH_USD_DEFAULT ))

    @property
    def GAS( self ):
        """Return Gas price oracle information, or empty dict"""
        return gasoracle( chain=self.chain )

    @property
    def LASTBLOCK( self ):
        """Ethereum Gas Fee estimate comes from this block; indicates if the self.GAS has been queried."""
        return int( self.GAS.get( 'LastBlock', 0 ))

    @property
    def GAS_GWEI( self ):
        """Ethereum aggregate (pre-EIP-1559) Gas Fee proposed, in GWEI.  This is the total Base +
        Priority fee to be paid, in Gwei per Gas, for the specified transaction Speed desired.  This
        would be the value you'd use for a traditional-style transaction with a "gasPrice" value.

        If we don't know, we'll just return a guess.  It is likely that you'll want to check if
        self.UPDATED, and do something else to compute your gas pricing -- such as ask your Ethereum
        blockchain what it suggests, via the JSON eth_maxPriorityFeePerGas API call, for example.

        """
        return float( self.GAS.get( self.speed.name+'GasPrice', self.GAS_GWEI_DEFAULT ))

    @property
    def GAS_WEI( self ):
        """Ethereum Gas Fee, in WEI"""
        return int( self.GAS_GWEI * self.GWEI_WEI )

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
            >>> maxFeePerGas = spend / ETH.GAS_USD ETH.GAS_WEI (TODO)

        """
        return self.ETH_USD * self.GAS_GWEI / self.ETH_GWEI

    @property
    def BASEFEE_GWEI( self ):
        """Ethereum Base Fee estimate for upcoming block, in GWEI (Etherscan API returns fees in Gwei/Gas).

        """
        return float( self.GAS.get( 'suggestBaseFee', self.BASEFEE_GWEI_DEFAULT ))

    @property
    def BASEFEE_WEI( self ):
        """Ethereum Base Fee, in WEI"""
        return int( self.BASEFEE_GWEI * self.GWEI_WEI )

    @property
    def PRIORITY_GWEI( self ):
        """Ethereum Priority Fee per Gas estimate for upcoming block, in GWEI.  Compute this by taking the
        Safe/Propose/Fast total Gas Price Fee estimate, and subtracting off the estimated Base Fee.

        This is what you'd supply if you want to use maxPriorityFeePerGas for your Ethereum
        transaction (actually, since they usually want it in Wei, use self.PRIORITY_WEI).

        """
        return self.GAS_GWEI - self.BASEFEE_GWEI

    @property
    def PRIORITY_WEI( self ):
        return int( self.PRIORITY_GWEI * self.GWEI_WEI )

    @property
    def UPDATED( self ):
        """If we successfully obtained Gas and Ethereum pricing, return the timestamp of the Ethereum."""
        return self.LASTBLOCK and self.TIMESTAMP

    @property
    def STATUS( self ):
        updated			= self.UPDATED
        if updated:
            return datetime.utcfromtimestamp( updated ).ctime() + " UTC"

    def __bool__( self ):
        """The GasOracle API requires a True result when maxPriorityFeePerGas is available."""
        return bool( self.UPDATED )

    def maxFeePerGas( self, spend=None, gas=None, max_factor=None ):
        """Returns new-style EIP-1559 max gas fees allowed, in Wei.  Computes a maxFeePerGas we're
        willing to pay per Gas, for max 'gas', to keep total transaction cost below 'spend'.

        If either is not specified, we'll simply cap it at a base fee + 'max_factor' x priority fee.

        Results are expressed in integer Wei.
        """
        assert isinstance( spend, (int,float,type(None))), \
            f"Require a numeric spend amount in USD$, not {spend!r}"
        assert isinstance( gas, (int,float,type(None))), \
            f"Require a numeric gas amount, not {gas!r}"
        if not spend or not gas:
            # Default: cap at some additional factor of the priority fee.
            return dict(
                maxFeePerGas	= self.BASEFEE_WEI + self.PRIORITY_WEI * ( max_factor or 2 )
            )

        # Otherwise, we can compute what we're willing to pay per Gas, from the specified total
        # spend allowed vs. gas estimate.  The transaction will not cost more than the specified
        # spend.  Requires a reasonable estimate of gas limit vs. the actual transaction Gas cost.

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

    def maxPriorityFeePerGas( self, spend=None, gas=None, max_factor=None ):
        """Returns new-style EIP-1559 gas Priority fee we'll likely need to pay, in Wei, to achieve the
        desired Speed (Safe, Propose or Fast).  This Priority Fee (plus the current network Base
        Fee) will be the Gas cost we'll pay, in Wei/Gas.

        If spend and gas is supplied, also includes the specific maxFeePerGas we're willing to spend.

        Results are expressed in integer Wei.
        """
        gas_price			= dict(
            maxPriorityFeePerGas	= self.PRIORITY_WEI,
        ) | self.maxFeePerGas( spend=spend, gas=gas, max_factor=max_factor )
        log.info(
            f"{self.chain}: EIP-1559 Gas Pricing at USD${self.ETH_USD:9,.2f}/ETH:"
            f" {gas_price['maxPriorityFeePerGas'] / self.GWEI_WEI:9,.2f} Priority + {self.BASEFEE_GWEI:9,.2f} Base Gwei/Gas"
            + (
                f"; for max USD${spend or gas * gas_price['maxFeePerGas'] * self.ETH_USD / self.ETH_WEI:9,.2f} per"
                f" {gas:10,}-Gas transaction: {gas_price['maxFeePerGas'] / self.GWEI_WEI:9,.2f} Gwei/Gas"
                if gas and 'maxFeePerGas' in gas_price
                else ""
            )
        )
        return gas_price

    def gasPrice( self ):
        """The traditional gasPrice interface.  Returns the total gasPrice we're willing to pay.

        """
        gas_price			= dict(
            gasPrice			= self.GAS_WEI,
        )
        log.info(
            f"{self.chain}: Traditional Gas Pricing: {gas_price['gasPrice'] / self.GWEI_WEI:9,.2f} Gwei/Gas"
        )
        return gas_price


#
# Optimize, and search for imports relative to this directory.
#
# Don't over-optimize, or construction code gets very big (and expensive to deploy)
#
solcx_options			= dict(
    optimize		= True,
    optimize_runs	= 100,
    # Any contract paths referenced from within contracts search relative to this
    base_path		= Path( __file__ ).resolve().parent
)
solc_version			= "0.8.17"


class Contract:
    """Interact with Ethereum contracts, via web3.py's web3.Web3 instance.

    Specify an ETHERSCAN_API_TOKEN to avoid the free tier's 1/5s call rate.  We always query the
    Ethereum chain via Etherscan (there is no gasoracle on it's Goerli API URL).

    Specify an ALCHEMY_API_TOKEN and use Alchemy's Goerli or Ethereum (default) APIs.

    Attempts to reload/compile the contract of the specified version, from the .source path.

    Does not clutter up the object() API with names, to avoid shadowing any normal Contract API
    functions starting with letters.

    If a GasOracle is supplied for gas_oracle, we'll use it. Otherwise, we'll fall back to just
    using the gas pricing recommended by our Web3 API provider.
    """

    def __init__(
        self,
        w3_provider,
        agent				= None,		# The Ethereum account of the agent accessing the Contract (if Gas required)
        agent_prvkey: Optional[bytes]	= None,		# Can only query public data, view methods without
        source: Optional[Path]		= None,
        version: Optional[str]		= None,
        name: Optional[str]		= None,
        address: Optional[str]		= None,
        abi: Optional[Dict]		= None,
        bytecode: Optional[bytes]	= None,
        chain: Optional[Chain]		= None,		# The Etherscan network to get data from (basically, always Ethereum)
        speed: Optional[Speed]		= None,		# The Etherscan Gas pricing selection for speed of transactions
        max_usd_per_gas:Optional[float]	= None,		# If not supplied, we'll set a cap of base fee + 2 x priority fee
        gas_oracle: Optional[GasOracle]	= None,
        gas_oracle_timeout: Optional[Tuple[int,float]] = None,  # None avoids waiting, doesn't check
    ):
        # If a GasOracle is supplied, we'll wait up to gas_oracle_timeout seconds for it to report
        # online.  Give it a tickle here to get it started, while we do other time-consuming stuff.
        self._gas_oracle	= GasOracle() if gas_oracle is None else gas_oracle
        gas_oracle_beg		= timer()
        bool( self._gas_oracle )

        self._w3		= Web3( w3_provider )
        self._agent		= agent
        if self._agent is not None:
            self._w3.eth.default_account = str( self._agent )

        if agent_prvkey:
            account_signing	= eth_account.Account.from_key( '0x' + agent_prvkey )
            assert account_signing.address == agent, \
                f"The agent Ethereum Account private key 0x{agent_prvkey} isn't related to agent account address {agent}"
            self._w3.middleware_onion.add(
                construct_sign_and_send_raw_middleware( account_signing ))

        self._address		= address		# An existing deployed contract

        self.__source		= source		# The Contract source path (compile for abi, or to deploy bytecode)
        self._version		= version
        self._name		= name or self.__class__.__name__
        self._abi		= abi
        self._bytescode		= bytecode
        self._max_usd_per_gas	= max_usd_per_gas       # 1.50/21000 --> up to $1.50 for a standard ETH transfer

        self._contract		= None
        self._compiled		= None
        if not self._abi:
            self._compile()

        # We've done all the stuff that may take some time; now, we may need the GasOracle
        # to be online.  Check, and wait if specified.
        if gas_oracle is not None and gas_oracle_timeout is not None:
            while not self._gas_oracle and timer() - gas_oracle_beg < gas_oracle_timeout:
                time.sleep( gas_oracle_timeout / 10 )
            if not self._gas_oracle:
                log.warning( f"Supplied GasOracle still offline after {timer() - gas_oracle_beg:7.2f}s" )

        if self._address:
            # A deployed contract; update any cached data, etc.
            self._contract	= self._w3.eth.contract( address=self._address, abi=self._abi )
            self._update()
        else:
            # Not yet deployed; lets use the provided or compiled ABI and bytecode
            assert self._bytecode, \
                "Must provide abi and bytecode, or Contract source"
            self._contract	= self._w3.eth.contract( abi=self._abi, bytecode=self._bytecode )

    @property
    def _source( self ):
        """Search for the named file, relative to the ., ./contracts/ and finally slip39/invoice/contracts/.

        Also used for caching artifacts related to that source file.

        """
        path			= Path( self.__source or self._name + '.sol' )
        if not path.is_absolute():
            for base in '.', 'contracts', solcx_options['base_path'] / 'contracts':
                check		= Path( base ) / path
                if check.exists():
                    path	= check
                    break
        if self._version is None:
            with open( path, 'rb' ) as f:
                self._version	= sha256( f.read() ).hexdigest()[:6].upper()
        log.info( f"Found {self._name} v{self._version}: {path}" )
        return path

    def _compile( self ):
        """Compiled or reload existing compiled contract.

        See if we've got this code compiled already, w/ the source code version, target solc
        compiler version, and optimization level

            ...sol-abc123-v0.8.17-o100

        """
        source			= self._source
        specs			= [
            '.sol',
            self._version,
            f"v{solc_version}",
        ]
        if {'optimize', 'optimize_runs'} <= set(solcx_options.keys()) and solcx_options['optimize']:
            specs.append( f"o{solcx_options['optimize_runs']}" )
        compiled		= source.with_suffix( '-'.join( specs ))
        if compiled.exists():
            self._compiled	= json.loads( compiled.read_text() )
            log.info( f"{self._name} Reloaded: {compiled}: {json.dumps( self._compiled, indent=4 )}" )
        else:
            self.compiled	= solcx.compile_files(
                source,
                output_values	= ['abi', 'bin'],
                solc_version	= solc_version,
                **solcx_options
            )
            compiled.write_text( json.dumps( self.compiled, indent=4 ))
            log.info( f"{self._name} Compiled: {compiled}: {json.dumps( self.compiled, indent=4 )}" )

        key			= self._abi_key( self._name, compiled )
        self._bytecode		= self._compiled[key]['bin']
        self._abi		= self._compiled[key]['abi']

    def _call( self, name, *args, gas=None, **kwds ):
        """Invoke function name on deployed contract w/ supplied positional args.  For example,
        to call a function we'd normally use:

            self._contract.functions.erc20s_len( ).call({ 'to': "0x", ... })
                                        *args --^       ^-- **kwds

        Since we've already defaulted the self._agent, all we need is the gas price.  But, pass
        any kwds as transaction options.

        The default is to pass 0 gas; must be a free transaction, such as a public value or
        'view' method.  This default will cause any Gas-consuming function call to fail.

        """
        try:
            func		= getattr( self._contract.functions, name )
            # If tx details or a gas limit is supplied, also provide gas pricing; this must be
            # intended to be a transaction to the blockchain.  Otherwise, assume this is a zero-cost
            # call, and provide no gas limit or pricing information.
            tx			= {}
            if kwds or gas:
                tx		= kwds | self._gas_price( gas=gas )
            log.info(  f"Calling {self._name}.{name}( {commas( args )} ) w/ tx: {tx!r}" )
            result		= func( *args ).call( tx )
            success		= True
        except Exception as exc:
            result		= repr( exc )
            success		= False
            raise
        finally:
            log.info( f"Called  {self._name}.{name}( {commas( args )} ) -{'-' if success else 'x'}> {result}" )
        return result

    def __getattr__( self, name ):
        """Assume any unknown attribute (not found in any normal way) .name is assumed to be a call to
        a Contract's API function.  Calls to Contract functions that collide w/ methods must be made via

            .call( name, *args, **kwds )

        All positional args are passed to the Contract API function.

        For functions requiring Gas, must supply a max gas= keyword estimate; any additional
        keywords are assumed to be transaction options.

        """
        def curry( *args, **kwds ):
            return self._call( name, *args, **kwds )
        return curry

    def _abi_key( self, name, path=None ):
        """Determine the ABI key for in .compiled source from 'path', matching contract 'name'"""
        try:
            key,		= ( k for k in self._compiled.keys() if k.endswith( f":{name}" ))
        except Exception as exc:
            raise KeyError( f"Failed to find ABI for Contract {name} in Solidity compiled from {path or self._source}" ) from exc
        return key

    def _update( self ):
        pass

    def _gas_price(
        self,
        gas,				# Estimated Gas required
        fail_fast	= None,		# If we predict failure due to gas * price, fail now
        max_factor	= None		# How much can Gas price increase before failing Tx?
    ):
        """Establish maxPriorityFeePerGas Gas fees for a transaction, optionally w/ a computed
        maxFeePerGas for the given estimated (max) amount of Gas required by the transaction.

        Gets the latest gas pricing information from the connected network to compute the Priority
        Fee required and the estimated Base Fee per Gas that the next block is likely to consume.
        From this, we can estimate what the likely total Fee per Gas is likely to be, in Wei.

        Then, uses estimated Ethereum (ETH) price and self._max_usd_per_gas to compute our
        maxFeePerGas.  If the estimated total Fee per Gas exceeds this limit, the transaction is
        likely to fail, and we'll issue a warning (or raise an Exception, if fail_fast is truthy).

        Otherwise, we'll return a Gas fee dict to use with the transaction.

        TODO: Use the Ethereum JSON-RPC spec and connect to a local node:

            https://ethereum.github.io/execution-apis/api-documentation/

        """

        # Find out what the network thinks the required Gas fees need to be.  This could be a
        # Testnet like Goerli, with abnormally low Gas prices.  But, for a real Ethereum Mainnet
        # transaction, it will be an estimate of the latest block's gas price estimates for the next
        # block.
        latest			= self._w3.eth.get_block( 'latest' )
        base_fee		= latest['baseFeePerGas']
        max_priority_fee	= self._w3.eth.max_priority_fee
        est_gas_wei		= base_fee + max_priority_fee
        max_gas_wei		= base_fee + max_priority_fee * ( max_factor or 2 )
        gas_info_network	= dict(
            maxPriorityFeePerGas	= max_priority_fee,     # Priority fee we're willing to pay, in Wei
            maxFeePerGas		= max_gas_wei,		# With a cap at double the priority fee
        )
        gas_info		= gas_info_network

        # Now, find out what Etherscan's Gas Oracle thinks (from the real Ethereum mainnet,
        # usually).  We'll always use these, if they're not estimated, because we want to simulate
        # real Gas costs even during testing.  However, if we don't have real, updated
        # readings, we'll fall back to the chain's recommendations.
        spend			= gas * self._max_usd_per_gas if gas and self._max_usd_per_gas else None
        if bool( self._gas_oracle ):
            # OK, whatever GasOracle was provided claims to be online; use it!
            try:
                gas_info_oracle	= self._gas_oracle.maxPriorityFeePerGas( gas=gas, spend=spend, max_factor=max_factor )
            except Exception as exc:
                log.warning( f"Gas Oracle API failed: {exc}; Using network estimate instead {traceback.format_exc() if log.isEnabledFor( logging.DEBUG ) else ''}"  )
            else:
                if max_fee_wei := gas_info_oracle.get( 'maxFeePerGas' ):
                    if max_fee_wei < est_gas_wei:
                        what		= f"Max Fee: {max_fee_wei / GasOracle.GWEI_WEI:,.4f} Gwei/Gas is below likely Fee: {est_gas_wei / GasOracle.GWEI_WEI:,.4f} Gwei/Gas"
                        if fail_fast:
                            raise RuntimeError( what + f"; Failing transaction on {self.__class__.__name__}" )
                        else:
                            log.warning( what )
                gas_info	= gas_info_oracle
        else:
            log.info( "Gas Oracle not updated; using network Gas estimates instead" )

        def gas_price_in_gwei( prices ):
            return {
                k: f"{v / GasOracle.GWEI_WEI:,.4f} Gwei == {v:,} Wei" if 'Gas' in k else v
                for k, v in prices.items()
            }

        log.info(
            f"Contract Transaction Gas Price: {json.dumps( gas_price_in_gwei( gas_info ), indent=4 )}" + (
                f"vs. network estimate: {json.dumps( gas_price_in_gwei( gas_info_network ), indent=4 )}" if gas_info != gas_info_network else ""
            )
        )

        # Finally, if a transaction gas limit was supplied, we are assuming this is a Gas-using
        # transaction -- pass it through as the starting Gas.
        if gas is not None:
            gas_info.update( gas=gas )
        return gas_info

    def _tx_gas_cost( self, tx, receipt ):
        """Compute a transaction's actual gas cost, in Wei.  We must get the block's baseFeePerGas, and
        add our transaction's "tip" maxPriorityFeePerGas.  All prices are in Wei/Gas.

        """
        block			= self._w3.eth.get_block( receipt.blockNumber )  # w/ Web3 Tester, may be None
        tx_idx			= receipt.transactionIndex
        base_fee		= block.baseFeePerGas
        prio_fee		= tx.maxPriorityFeePerGas
        log.debug( f"Block {block.number!r:10} base fee: {base_fee/GasOracle.GWEI_WEI:7.4f}Gwei + Tx #{tx_idx!r:4} prio fee: {prio_fee/GasOracle.GWEI_WEI:7.4f}Gwei" )
        return base_fee + prio_fee

    def _deploy( self, *args, gas=None, **kwds ):
        """Create an instance of Contract, passing args to the constructor, and kwds to the transaction.

        Once deployed, we can _update.  However, the contract will not be available for subsequent
        calls until the block is accepted.

        """
        assert not self._address, \
            f"You already have an instance of Contract {self._name}: {self._address}"
        assert gas, \
            f"You must specify an estimated gas amount to deploy a Contract, found: {gas}"

        cons_hash		= self._contract.constructor( *args ).transact( kwds | self._gas_price( gas=gas ))
        log.info( f"Web3 Construct {self._name} hash: {cons_hash.hex()}" )
        cons_tx			= self._w3.eth.get_transaction( cons_hash )
        log.info( f"Web3 Construct {self._name} tx: {json.dumps( cons_tx, indent=4, default=str )}" )
        cons_receipt		= self._w3.eth.wait_for_transaction_receipt( cons_hash )
        log.info( f"Web3 Construct {self._name} receipt: {json.dumps( cons_receipt, indent=4, default=str )}" )
        assert cons_receipt.status, \
            f"Deployment of contract was not successful; status == {cons_receipt.status}"

        # The Contract was successfully deployed.  Get its address, and provide an interface to it.
        self._address		= cons_receipt.contractAddress
        self._contract		= self._w3.eth.contract( address=self._address, abi=self._abi )
        gas_cost		= self._tx_gas_cost( cons_tx, cons_receipt )
        log.warning( f"Web3 Construct {self._name} Contract: {len(self._bytecode)} bytes, at Address: {self._address}" )
        log.info( "Web3 Construct {} Gas Used: {} == {:7.4f}Gwei == USD${:9,.2f} ({}): ${:.6f}/byte".format(
            self._name,
            cons_receipt.gasUsed,
            cons_receipt.gasUsed * gas_cost / GasOracle.GWEI_WEI,
            cons_receipt.gasUsed * gas_cost * self._gas_oracle.ETH_USD / GasOracle.ETH_WEI, self._gas_oracle or 'estimated',
            cons_receipt.gasUsed * gas_cost * self._gas_oracle.ETH_USD / GasOracle.ETH_WEI / len( self._bytecode ),
        ))

        # Wait for the next block to be mined, to ensure contract is available for use.  Is this
        # necessary?  Once the Contract receipt is available, perhaps this means that the block has
        # been mined and is ready for API access.  Otherwise, use '<=' here to wait for next block.
        beg			= timer()
        while ( block_number := self._w3.eth.block_number ) < cons_receipt.blockNumber:
            time.sleep( 1 )
        log.info( f"Waited {timer()-beg:.2f}s for block {block_number} to be mined, vs. Contract block: {cons_receipt.blockNumber}" )

        self._update()


offchainoracle_address		= '0x07D91f5fb9Bf7798734C3f606dB065549F6893bb'
offchainoracle_abi		= [{"inputs":[{"internalType":"contract MultiWrapper","name":"_multiWrapper","type":"address"},{"internalType":"contract IOracle[]","name":"existingOracles","type":"address[]"},{"internalType":"enum OffchainOracle.OracleType[]","name":"oracleTypes","type":"uint8[]"},{"internalType":"contract IERC20[]","name":"existingConnectors","type":"address[]"},{"internalType":"contract IERC20","name":"wBase","type":"address"}],"stateMutability":"nonpayable","type":"constructor"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract IERC20","name":"connector","type":"address"}],"name":"ConnectorAdded","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract IERC20","name":"connector","type":"address"}],"name":"ConnectorRemoved","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract MultiWrapper","name":"multiWrapper","type":"address"}],"name":"MultiWrapperUpdated","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract IOracle","name":"oracle","type":"address"},{"indexed":False,"internalType":"enum OffchainOracle.OracleType","name":"oracleType","type":"uint8"}],"name":"OracleAdded","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"internalType":"contract IOracle","name":"oracle","type":"address"},{"indexed":False,"internalType":"enum OffchainOracle.OracleType","name":"oracleType","type":"uint8"}],"name":"OracleRemoved","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"internalType":"address","name":"previousOwner","type":"address"},{"indexed":True,"internalType":"address","name":"newOwner","type":"address"}],"name":"OwnershipTransferred","type":"event"},{"inputs":[{"internalType":"contract IERC20","name":"connector","type":"address"}],"name":"addConnector","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IOracle","name":"oracle","type":"address"},{"internalType":"enum OffchainOracle.OracleType","name":"oracleKind","type":"uint8"}],"name":"addOracle","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"connectors","outputs":[{"internalType":"contract IERC20[]","name":"allConnectors","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"srcToken","type":"address"},{"internalType":"contract IERC20","name":"dstToken","type":"address"},{"internalType":"bool","name":"useWrappers","type":"bool"}],"name":"getRate","outputs":[{"internalType":"uint256","name":"weightedRate","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"srcToken","type":"address"},{"internalType":"bool","name":"useSrcWrappers","type":"bool"}],"name":"getRateToEth","outputs":[{"internalType":"uint256","name":"weightedRate","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"multiWrapper","outputs":[{"internalType":"contract MultiWrapper","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"oracles","outputs":[{"internalType":"contract IOracle[]","name":"allOracles","type":"address[]"},{"internalType":"enum OffchainOracle.OracleType[]","name":"oracleTypes","type":"uint8[]"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"owner","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"connector","type":"address"}],"name":"removeConnector","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IOracle","name":"oracle","type":"address"},{"internalType":"enum OffchainOracle.OracleType","name":"oracleKind","type":"uint8"}],"name":"removeOracle","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"renounceOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract MultiWrapper","name":"_multiWrapper","type":"address"}],"name":"setMultiWrapper","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"newOwner","type":"address"}],"name":"transferOwnership","outputs":[],"stateMutability":"nonpayable","type":"function"}]  # noqa: E501

ierc20metadata_abi		= [
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "spender",
                "type": "address"
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "value",
                "type": "uint256"
            }
        ],
        "name": "Approval",
        "type": "event"
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "value",
                "type": "uint256"
            }
        ],
        "name": "Transfer",
        "type": "event"
    },
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "owner",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "spender",
                "type": "address"
            }
        ],
        "name": "allowance",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "spender",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            }
        ],
        "name": "approve",
        "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "account",
                "type": "address"
            }
        ],
        "name": "balanceOf",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [
            {
                "internalType": "uint8",
                "name": "",
                "type": "uint8"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "name",
        "outputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [
            {
                "internalType": "string",
                "name": "",
                "type": "string"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [
            {
                "internalType": "uint256",
                "name": "",
                "type": "uint256"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            }
        ],
        "name": "transfer",
        "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "address",
                "name": "from",
                "type": "address"
            },
            {
                "internalType": "address",
                "name": "to",
                "type": "address"
            },
            {
                "internalType": "uint256",
                "name": "amount",
                "type": "uint256"
            }
        ],
        "name": "transferFrom",
        "outputs": [
            {
                "internalType": "bool",
                "name": "",
                "type": "bool"
            }
        ],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

#
# Some tokens such as Maker(MKR) implement ERC-20 w/o the standard, optional symbols/name; they use
# bytes32 (and uint256 for digits), eg.:
#
#    https://etherscan.io/address/0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2#code
#
ierc20bytes32_abi		= [
    {"constant":True,"inputs":[],"name":"name",    "outputs":[{"name":"","type":"bytes32"}],"payable":False,"stateMutability":"view","type":"function"},
    {"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},
    {"constant":True,"inputs":[],"name":"symbol",  "outputs":[{"name":"","type":"bytes32"}],"payable":False,"stateMutability":"view","type":"function"},
]


#
# An example of one way to cache Web3 connections
#
# WARNING:
# - Not thread-safe.  These cached providers need to be used by a single thread
# - Caches results w/ differing use_provider=, for the same w3_url
# - We do not normalize addresses; use Ethereum addresses that have corect checksums
#
@memoize( maxage=None, maxsize=None, log_at=logging.INFO )
def w3_provider( w3_url, use_provider ):
    """Return a Web3.*Provider associated with the specified URL, optionally using the specified
    provider."""
    if use_provider is None:
        use_provider		= dict(
            wss		= Web3.WebsocketProvider,
            http	= Web3.HTTPProvider,
            https	= Web3.HTTPProvider,
        )[w3_url.split( ':', 1 )[0].lower()]
    return use_provider( w3_url )


@dataclass( eq=True, frozen=True )      # Makes it hashable
class TokenInfo:
    """Represents a Crypto-currency or on-chain Token (eg. ERC-20)"""
    symbol: str
    name: str
    decimals: int
    contract: Optional[str] = None      # If not an ERC-20 token contract, no contract address
    icon: Optional[Union[str,Path]] = None


def tokeninfo( token, chain=None, w3_url=None, use_provider=None ):
    """Lookup or query the specified token for the specified chain w/ the specified API w3_url, by
    symbol, name, un-normalized or normalized (w/ valid checksum) address.  The first time a Token
    is looked up, its contract address must be used; subsequently, a case-insensitive symbol
    (upper-case) or name (lower-case) may be used.  Tokens with names/symbols identical except for
    case are disambiguated by upper/lower case correction.  Thus, two tokens may have a 'name'
    identical to another's 'symbol', yet not collide.

    Loads the known (top few hundred) Tokens for the chain on first call, to:
    - Avoid needing to reach out to the Ethereum blockchain for well-known tokens
    - To check for "trojan" tokens trying to impersonate well-known tokens on a chain

    This is subtle; since we can look up tokens on various blockchains, and the "same" token
    (eg. USDC, WEENUS) can appear on various blockchains with different contract addresses, we don't
    want to have collisions.  So, each chain must have its own cache of contract/symbol/names.

    Since we are already caching here, we don't use memoize; any w3_url targeting the same chain is
    considered identical.

    """
    try:
        token			= Web3.to_checksum_address( token )
    except ValueError:
        pass
    if chain and isinstance( chain, str ):  # The blockchain; eg. "Ethereum", "Goerli"
        chain,			= ( c for c in Chain if c.name.lower() == chain.lower() )
    assert isinstance( chain, (Chain, type(None)) )
    if chain is None:
        chain			= Chain.Ethereum
    if w3_url is None:
        w3_url			= alchemy_url( chain  )

    def aliasinfo( info ):
        cont			= info.contract
        assert cont not in tokeninfo.ERC20s[chain], \
            f"Duplicate ERC-20 contract address {info.contract!r} on {chain}"
        symb			= info.symbol.upper()
        assert symb not in tokeninfo.ERC20s[chain], \
            f"Duplicate ERC-20 symbol {info.symbol!r} on {chain}"
        name			= info.name.lower()
        assert name not in tokeninfo.ERC20s[chain], \
            f"Duplicate ERC-20 name {info.name!r} on {chain}"
        tokeninfo.ERC20s[chain][cont] = info
        tokeninfo.ERC20s[chain][symb] = info
        tokeninfo.ERC20s[chain][name] = info
        return info

    # If token is known in ./Tokens-<chain>.json, return it.  Iff the stated icon file exists,
    # include its Path, else None.  Defaults to an empty dict for each chain.
    if not tokeninfo.ERC20s.setdefault( chain, {} ):
        here			= Path( __file__ ).resolve().parent
        here_json		= here / f"Tokens-{chain.name}.json"
        try:
            loaded		= -1
            if here_json.exists():
                with open( here_json, 'r' ) as json_f:
                    for loaded,info in enumerate( json.loads( json_f.read() )):
                        if icon := info.get( 'icon' ):
                            icon_p	= here / icon
                            if icon_p.exists():
                                info['icon'] = icon_p.resolve()
                            else:
                                info['icon'] = None
                                log.warning( f"ERC-20 token {info['symbol']} references non-existent icon {icon_p}" )
                        aliasinfo( TokenInfo( **info ))
        except Exception as exc:
            log.warning( f"Failed to load known ERC-20 tokens for {chain} from {here_json}: {exc}" )
        else:
            log.warning( f"Loaded {loaded+1} known ERC-20 tokens for {chain} from {here_json}" )

    # Either the contract address w/ checksum, symbol (upper-case) or name (lower-case) may be
    # present in the chain's cache.
    for t in (token, token.upper(), token.lower(), INVOICE_PROXIES.get( token.upper() ), INVOICE_PROXIES.get( token.lower() )):
        if info := tokeninfo.ERC20s[chain].get( t ):
            return info

    # Not (yet) a known token for chain; we'll have to query the blockchain for this token's data.
    # It must, therefore, be a normalized contract address.
    assert Web3.is_checksum_address( token ), \
        f"Cannot query ERC-20 token contract address: {token}; must be valid address w/checksum"
    w3				= Web3( w3_provider( w3_url, use_provider ))
    token_ierc20metadata	= w3.eth.contract( address=token, abi=ierc20metadata_abi )
    try:
        decimals		= token_ierc20metadata.functions.decimals().call()
        symbol			= token_ierc20metadata.functions.symbol().call()
        name			= token_ierc20metadata.functions.name().call()
    except Exception:
        # Hmm.  Some top-100 tokens fail to respond correctly to the standard IERC20MetaData API.
        # Try another commonly used API.  If this raises an Exception, let it through.
        token_ierc20bytes32	= w3.eth.contract( address=token, abi=ierc20bytes32_abi )
        decimals		= token_ierc20bytes32.functions.decimals().call()
        symbol			= token_ierc20bytes32.functions.symbol().call().strip( b'\0' ).decode( 'utf-8' )
        name			= token_ierc20bytes32.functions.name().call().strip( b'\0' ).decode( 'utf-8' )

    # Remember this token; this will fail if it collides w/ a "known" token.
    return aliasinfo( TokenInfo(
        name		= name,
        symbol		= symbol,
        decimals	= decimals,
        contract	= token,
        icon		= None,
    ))
tokeninfo.ERC20s		= {}  # noqa: E305; { <chain>: {'contract': <info>, 'name': <info>, 'symbol': info, ... }}


def tokenknown( name, decimals=None ):
    """If name is a recognized core supported Cryptocurrency, return a TokenInfo useful for formatting.

    Since Bitcoin (and other similar cryptocurrencies) are typically assumed to have 8 decimal
    places (a Sat(oshi) is 1/10^8 of a Bitcoin), we'll make the default decimals//3 precision work
    out to 8).

    """
    try:
        symbol			= Account.supported( name )
    except ValueError as exc:
        log.info( f"Failed to identify currency {name!r} as a supported Cryptocurrency: {exc}" )
        raise
    return TokenInfo(
        symbol		= symbol,
        name		= Account.CRYPTO_SYMBOLS[symbol],
        decimals	= Account.CRYPTO_DECIMALS[symbol] if decimals is None else decimals,
        icon		= next( ( Path( __file__ ).resolve().parent / "Cryptos" ).glob( symbol + '*.*' ), None ),
    )


@memoize( maxage=TOKPRICES_MEMO_MAXAGE, maxsize=TOKPRICES_MEMO_MAXSIZE, log_at=logging.INFO )
def tokenprice( w3_url, chain, token, base, use_wrappers=None, use_provider=None ):
    """Return memoized token address prices, in terms of a base token address.  The resultant Fraction
    is the ratio token/base (if token is greater in value than base, the ratio will be > 1).  If
    None supplied for base, uses Ethereum.

    Queries and returns the tokens' TokenInfo and the price ratio as a Fraction.

    """
    w3				= Web3( w3_provider( w3_url, use_provider ))
    if use_wrappers is None:
        use_wrappers		= True

    token_info			= tokeninfo( token, w3_url=w3_url, chain=chain, use_provider=use_provider )

    offchainoracle_contract	= w3.eth.contract( address=offchainoracle_address, abi=offchainoracle_abi)
    if base is None:
        base_info		= TokenInfo(
            name	= "Ethereum",
            symbol	= "ETH",
            decimals	= 18,
        )
        token_price		= offchainoracle_contract.functions.getRateToEth( token_info.contract, use_wrappers ).call()
    else:
        base_info		= tokeninfo( base, w3_url=w3_url, chain=chain, use_provider=use_provider )
        token_price		= offchainoracle_contract.functions.getRate(
            token_info.contract, base_info.contract, use_wrappers,
        ).call()
    price			= Fraction( token_price, 10 ** 18 )
    price		       *= Fraction( 10 ** token_info.decimals, 10 ** base_info.decimals )
    return token_info, base_info, price


#
# Public APIs for token{infos,prices,ratio}
#
# Defaults to Alchemy API on Ethereum MainNet chain, searches/normalizes token addresses (from
# eg. ./Tokens-Ethereum.json).
#
def tokeninfos( *tokens, **kwds ):
    for token in tokens:
        yield tokeninfo( token, **kwds )


def tokenprices( *tokens, chain=None, w3_url=None, base=None, use_provider=None, use_wrappers=True ):
    """Return a sequence of token prices as a Fraction, optionally in terms of a base token (ETH is
    default).  Will default to use the Ethereum blockchain via the Alchemy API.

    TODO: should use MultiCallContract.multicall to aggregate several getRate... calls into one
    invocation: https://github.com/1inch/spot-price-aggregator/blob/master/examples/multiple-prices.js

    """
    if chain and isinstance( chain, str ):
        chain,			= ( c for c in Chain if c.name.lower() == chain.lower() )
    assert isinstance( chain, (Chain, type(None)) )
    if chain is None:
        chain			= Chain.Ethereum
    if w3_url is None:
        w3_url			= alchemy_url( chain )
    for token in tokens:
        token_addr		= tokeninfo( token, w3_url=w3_url, chain=chain, use_provider=use_provider ).contract
        base_addr		= None
        if base:
            base_addr		= tokeninfo( base,  w3_url=w3_url, chain=chain, use_provider=use_provider ).contract
        yield tokenprice( w3_url, chain, token_addr, base_addr, use_wrappers=use_wrappers, use_provider=use_provider )


def tokenratio( t1, t2, **kwds):
    """Find the price ratio of tokens t1/t2, optionally relative to a certain base token (should be
    irrelevant, as the default will be the main token in the chain, eg. ETH for the Ethereum MainNet.

    """
    (t1_i,_,t1_p),(t2_i,_,t2_p)	= tokenprices( t1, t2, **kwds )
    return t1_i,t2_i,t1_p/t2_p
