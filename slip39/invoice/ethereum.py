
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

from datetime		import datetime
from enum		import Enum
from pathlib		import Path
from hashlib		import sha256
from typing		import Dict, Optional

import requests
import eth_account
import eth_abi
import solcx

from rlp		import encode as rlp_encode
from web3		import Web3
from web3.middleware	import construct_sign_and_send_raw_middleware

from ..util		import memoize, retry, commas
from ..defaults		import ETHERSCAN_MEMO_MAXAGE, ETHERSCAN_MEMO_MAXSIZE
from ..util		import into_bytes

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

    if nonce is not None and salt is None and creation is None and creation_hash:
        # A CREATE (traditional, or transaction-based) contract creation
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


etherscan_urls			= dict(
    Ethereum	= 'https://api.etherscan.io/api',
    Goerli	= 'https://api-goerli.etherscan.io/api',
)


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
    BASEFEE_GWEI_DEFAULT	= 10.0
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
            >>> maxFeePerGas = spend / ETH.GAS_USD ETH.GAS_WEI

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
            f"{self.chain}: EIP-1559 Gas Pricing at USD${self.ETH_USD:9,.2f}/ETH: : {gas_price['maxPriorityFeePerGas'] / self.GWEI_WEI:9,.2f} Priority + {self.BASEFEE_GWEI:9,.2f} Base Gwei/Gas"
            + (
                f"; for max USD${spend or gas * gas_price['maxFeePerGas'] * self.ETH_USD / self.ETH_WEI:9,.2f} per {gas:10,}-Gas transaction: {gas_price['maxFeePerGas'] / self.GWEI_WEI:9,.2f} Gwei/Gas"  # noqa E501
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

    """

    def __init__(
        self,
        w3_provider,
        agent,						# The Ethereum account of the agent accessing the Contract
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
    ):
        self.ETH		= Etherscan( chain=chain, speed=speed )
        self.w3			= Web3( w3_provider )

        self.agent		= agent
        self.w3.eth.default_account = str( self.agent )
        if agent_prvkey:
            account_signing	= eth_account.Account.from_key( '0x' + agent_prvkey )
            assert account_signing.address == agent, \
                f"The agent Ethereum Account private key 0x{agent_prvkey} isn't related to agent account address {agent}"
            self.w3.middleware_onion.add(
                construct_sign_and_send_raw_middleware( account_signing ))

        self.address		= address		# An existing deployed contract

        self._source		= source		# The Contract source path (compile for abi, or to deploy bytecode)
        self.version		= version
        self.name		= name or self.__class__.__name__
        self.abi		= abi
        self.bytescode		= bytecode
        self.max_usd_per_gas	= max_usd_per_gas       # 1.50/21000 --> up to $1.50 for a standard ETH transfer

        self.contract		= None
        self.compiled		= None
        if not self.abi:
            self.compile()

        if self.address:
            # A deployed contract; update any cached data, etc.
            self.contract	= self.w3.eth.contract( address=self.address, abi=self.abi )
            self.update()
        else:
            # Not yet deployed; lets use the provided or compiled ABI and bytecode
            assert self.bytecode, \
                "Must provide abi and bytecode, or source"
            self.contract	= self.w3.eth.contract( abi=self.abi, bytecode=self.bytecode )

    @property
    def source( self ):
        """Search for the named file, relative to the ., ./contracts/ and finally slip39/invoice/contracts/.

        Also used for caching artifacts related to that source file.

        """
        path			= Path( self._source or self.name + '.sol' )
        if not path.is_absolute():
            for base in '.', 'contracts', solcx_options['base_path'] / 'contracts':
                check		= Path( base ) / path
                if check.exists():
                    path	= check
                    break
        if self.version is None:
            with open( path, 'rb' ) as f:
                self.version	= sha256( f.read() ).hexdigest()[:6].upper()
        log.info( f"Found {self.name} v{self.version}: {path}" )
        return path

    def compile( self ):
        """Compiled or reload existing compiled contract.

        See if we've got this code compiled already, w/ the source code version, target solc
        compiler version, and optimization level

            ...sol-abc123-v0.8.17-o100

        """
        source			= self.source
        specs			= [
            '.sol',
            self.version,
            f"v{solc_version}",
        ]
        if {'optimize', 'optimize_runs'} <= set(solcx_options.keys()) and solcx_options['optimize']:
            specs.append( f"o{solcx_options['optimize_runs']}" )
        compiled		= source.with_suffix( '-'.join( specs ))
        if compiled.exists():
            self.compiled	= json.loads( compiled.read_text() )
            log.info( f"{self.name} Reloaded: {compiled}: {json.dumps( self.compiled, indent=4, default=str )}" )
        else:
            self.compiled	= solcx.compile_files(
                source,
                output_values	= ['abi', 'bin'],
                solc_version	= solc_version,
                **solcx_options
            )
            compiled.write_text( json.dumps( self.compiled, indent=4 ))
            log.info( f"{self.name} Compiled: {compiled}: {json.dumps( self.compiled, indent=4, default=str )}" )

        key			= self.abi_key( self.name, compiled )
        self.bytecode		= self.compiled[key]['bin']
        self.abi		= self.compiled[key]['abi']

    def contract_call( self, name, *args, gas=None, **kwds ):
        """Invoke function name on deployed contract w/ supplied positional args.  For example,
        to call a function we'd normally use:

            self.contract.functions.erc20s_len( ).call({ 'from': self.agent })
                                               ^-- *args

        Since we've already defaulted the self.agent, all we need is the gas price.  But, pass
        any kwds as transaction options.

        The default is to pass 0 gas; must be a free transaction, such as a public value or
        view-only method.  This default will cause any Gas-consuming function call to fail.

        """
        try:
            func		= getattr( self.contract.functions, name )
            # If tx details or a gas limit is supplied, also provide gas pricing; this must be
            # intended to be a transaction to the blockchain.  Otherwise, assume this is a zero-cost
            # call, and provide no gas limit or pricing information.
            tx			= {}
            if kwds or gas:
                tx		= kwds | self.gas_price( gas=gas )
            log.info(  f"Calling {self.name}.{name}( {commas( args )} ) w/ tx: {tx!r}" )
            result		= func( *args ).call( tx )
            success		= True
        except Exception as exc:
            result		= repr( exc )
            success		= False
            raise
        finally:
            log.warning( f"Called  {self.name}.{name}( {commas( args )} ) -{'-' if success else 'x'}> {result}" )
        return result

    def __getattr__( self, name ):
        """Assume any unknown attribute (not found in any normal way) .name is assumed to be a call to
        a Contract's API function.

        All positional args are passed to the Contract API function.

        For functions requiring Gas, must supply a max gas= keyword estimate; any additional
        keywords are assumed to be transaction options.

        """
        def curry( *args, **kwds ):
            return self.contract_call( name, *args, **kwds )
        return curry

    def abi_key( self, name, path=None ):
        """Determine the ABI key for in .compiled source from 'path', matching contract 'name'"""
        try:
            key,		= ( k for k in self.compiled.keys() if k.endswith( f":{name}" ))
        except Exception as exc:
            raise KeyError( f"Failed to find ABI for Contract {name} in Solidity compiled from {path or self.source}" ) from exc
        return key

    def update( self ):
        pass

    def gas_price( self, gas, fail_fast=None, max_factor=None ):
        """Establish maxPriorityFeePerGas Gas fees for a transaction, optionally w/ a computed
        maxFeePerGas for the given estimated (max) amount of Gas required by the transaction.

        Gets the latest gas pricing information from the connected network to compute the Priority
        Fee required and the estimated Base Fee per Gas that the next block is likely to consume.
        From this, we can estimate what the likely total Fee per Gas is likely to be, in Wei.

        Then, uses estimated Ethereum (ETH) price and self.max_usd_per_gas to compute our
        maxFeePerGas.  If the estimated total Fee per Gas exceeds this limit, the transaction is
        likely to fail, and we'll issue a warning (or raise an Exception, if fail_fast is truthy).

        Otherwise, we'll return a Gas fee dict to use with the transaction.

        TODO: Use the Ethereum JSON-RPC spec and connect to a local node:

            https://ethereum.github.io/execution-apis/api-documentation/

        """

        # Find out what the network thinks the required Gas fees need to be.  This could be a
        # Testnet like Goerli, with abnormally low Gas prices.
        latest			= self.w3.eth.get_block( 'latest' )
        base_fee		= latest['baseFeePerGas']
        max_priority_fee	= self.w3.eth.max_priority_fee
        est_gas_wei		= base_fee + max_priority_fee
        max_gas_wei		= base_fee + max_priority_fee * ( max_factor or 2 )
        gas_info_network	= dict(
            maxPriorityFeePerGas	= max_priority_fee,     # Priority fee we're willing to pay, in Wei
            maxFeePerGas		= max_gas_wei,		# With a cap at double the priority fee
        )
        gas_info		= gas_info_network

        # Now, find out what Etherscan's Gas Oracle thinks (from the real Ethereum mainnet,
        # usually).  We'll always use these, if they're not estimated, because we want to simulate
        # real Gas costs even during testing.  However, if we don't have real, self.ETH.UPDATED
        # readings, we'll fall back to the chain's recommendations.
        spend			= gas * self.max_usd_per_gas if gas and self.max_usd_per_gas else None
        try:
            gas_info_oracle	= self.ETH.maxPriorityFeePerGas( gas=gas, spend=spend, max_factor=max_factor )
        except Exception as exc:
            log.warning( f"Gas Oracle API failed: {exc}; Using network estimate instead {traceback.format_exc() if log.isEnabledFor( logging.DEBUG ) else ''}"  )
        else:
            if self.ETH.UPDATED:
                if max_fee_wei := gas_info_oracle.get( 'maxFeePerGas' ):
                    if max_fee_wei < est_gas_wei:
                        what		= f"Max Fee: {max_fee_wei / self.ETH.GWEI_WEI:,.4f} Gwei/Gas is below likely Fee: {est_gas_wei / self.ETH.GWEI_WEI:,.4f} Gwei/Gas"
                        if fail_fast:
                            raise RuntimeError( what + f"; Failing transaction on {self.__class__.__name__}" )
                        else:
                            log.warning( what )
                gas_info	= gas_info_oracle
            else:
                log.warning( f"Gas Oracle not updated; using network Gas estimates instead {traceback.format_exc() if log.isEnabledFor( logging.DEBUG ) else ''}" )

        def gas_price_in_gwei( prices ):
            return {
                k: f"{v / self.ETH.GWEI_WEI:,.4f} Gwei" if 'Gas' in k else v
                for k, v in prices.items()
            }

        log.info(
            f"Contract Transaction Gas Price: {json.dumps( gas_price_in_gwei( gas_info ), indent=4 )}" + (
                f"vs. network estimate: {json.dumps( gas_price_in_gwei( gas_info_network ), indent=4 )}" if gas_info != gas_info_network else ""
            )
        )

        if gas is not None:
            gas_info.update( gas=gas )
        return gas_info

    def instantiate( self, *args, gas=None, **kwds ):
        """Create an instance of Contract, passing args to the constructor, and kwds to the transaction.

        """
        assert not self.address, \
            f"You already have an instance of Contract {self.name}: {self.address}"

        cons_hash		= self.contract.constructor( *args ).transact( kwds | self.gas_price( gas=gas ))
        log.info( f"Web3 Construct {self.name} hash: {cons_hash.hex()}" )
        cons_tx			= self.w3.eth.get_transaction( cons_hash )
        log.info( f"Web3 Construct {self.name} tx: {json.dumps( cons_tx, indent=4, default=str )}" )
        cons_receipt		= self.w3.eth.wait_for_transaction_receipt( cons_hash )
        log.info( f"Web3 Construct {self.name} receipt: {json.dumps( cons_receipt, indent=4, default=str )}" )
        self.address		= cons_receipt.contractAddress

        log.warning( f"Web3 Construct {self.name} Contract: {len(self.bytecode)} bytes, at Address: {self.address}" )
        log.info( "Web3 Tester Construct {} Gas Used: {} == {}gwei == USD${:9,.2f} ({}): ${:.6f}/byte".format(
            self.name,
            cons_receipt.gasUsed,
            cons_receipt.gasUsed * self.ETH.GAS_GWEI,
            cons_receipt.gasUsed * self.ETH.GAS_GWEI * self.ETH.ETH_USD / self.ETH.ETH_GWEI, self.ETH.STATUS or 'estimated',
            cons_receipt.gasUsed * self.ETH.GAS_GWEI * self.ETH.ETH_USD / self.ETH.ETH_GWEI / len( self.bytecode ),
        ))
