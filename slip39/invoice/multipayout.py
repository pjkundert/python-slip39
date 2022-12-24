
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

from fractions		import Fraction
from itertools		import count

from web3		import Web3		# noqa F401

from ..api		import account
from .ethereum		import Chain, Contract  # noqa F401

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( 'multipayout' )

goerli_account			= None
goerli_xprvkey			= os.getenv( 'GOERLI_XPRVKEY' )
if not goerli_xprvkey:
    goerli_seed			= os.getenv( 'GOERLI_SEED' )
    if goerli_seed:
        try:
            # why m/44'/1'?  Dunno.  That's the derivation path Trezor Suite uses for Goerli wallets...
            goerli_xprvkey	= account( goerli_seed, crypto="ETH", path="m/44'/1'/0'" ).xprvkey
        except Exception:
            pass
        # Using the "xprv..." key, and derive the 1st sub-account, on the combined path m/44'/1'/0'/0/0
        goerli_account		= account( goerli_xprvkey, crypto='ETH', path="m/0/0" )


alchemy_urls			= dict(
    Ethereum	= 'eth-mainnet.g.alchemy.com/v2',
    Goerli	= 'eth-goerli.g.alchemy.com/v2',
)


def alchemy_url( chain, protocol='wss' ):
    return f"{protocol}://{alchemy_urls[chain.name]}/{os.getenv( 'ALCHEMY_API_TOKEN' )}"


class MultiPayoutERC20( Contract ):
    """Provide access to our MultiPayoutERC20 Contract.

        >>> assert os.getenv( 'ETHERSCAN_API_TOKEN' )
        >>> assert os.getenv( 'ALCHEMY_API_TOKEN' )
        >>> assert goerli_account
        >>> mp = MultiPayoutERC20( Web3.WebsocketProvider( alchemy_url( Chain.Goerli )),
        ...    agent		= goerli_account.address,
        ...    agent_prvkey	= goerli_account.prvkey,
        ...    address		= "0x8b3D24A120BB486c2B7583601E6c0cf37c9A2C04"
        ... )
        >>> print( json.dumps( mp._payees, indent=4, default=lambda f: f"{float( f * 100 ):9.5f}%" ))
        {
            "0x7Fc431B8FC8250A992567E3D7Da20EE68C155109": "  6.59637%",
            "0xEeC2b464c2f50706E3364f5893c659edC9E4153A": " 35.09335%",
            "0xE5714055437154E812d451aF86239087E0829fA8": " 58.31028%"
        }
        >>> print( json.dumps( mp._erc20s, indent=4 ))
        {
            "0xe802376580c10fE23F027e1E19Ed9D54d4C9311e": [
                "USDT",
                6
            ],
            "0xde637d4C445cA2aae8F782FFAc8d2971b93A4998": [
                "USDC",
                6
            ],
            "0xaFF4481D10270F50f203E0763e2597776068CBc5": [
                "WEENUS",
                18
            ],
            "0x1f9061B953bBa0E36BF50F21876132DcF276fC6e": [
                "ZEENUS",
                0
            ]
        }

    TODO: This is a quite complex test with a lot of prerequisites; perhaps move from doctest to pytest
    """
    def __init__( self, *args, **kwds ):
        self._erc20s		= dict()		# [ <ERC-20 address>: ("<symbol>",<decimals>), ... ]
        self._payees		= dict()		# { <Payee address>: <Fraction>, ... }
        self._forwarder_hash	= None			# Keccack has of the Forwarder constructor bytecode for CREATE2
        super().__init__( *args, **kwds )

    def _update( self ):
        """Query the deployed MultiPayoutERC20 Contract to get payees and the (currently) specified
        ERC-20 tokens (<symbol>, <decimals>).

        Computes the Fraction representing the portion paid to each payee.

        TODO: recursively descend into payees that are also MultiPayoutERC20 contracts, and deduce
        the full tree of payees, and their aggregate percentages.

        """
        self._forwarder_hash	= self.forwarder_hash()
        log.info( f"{self._name} Forwarder CREATE2 hash: 0x{self._forwarder_hash.hex()}" )
        remaining		= Fraction( 1 )
        for i in count():
            payee, reserve	= self.payees( i )
            remaining_after	= remaining * Fraction( reserve, 2 ** 16 )  # TODO: get constant denominator from contract
            self._payees[payee]	= remaining - remaining_after
            if not reserve:
                break  # final payee must have zero reserve
            remaining		= remaining_after

        payees_json		= json.dumps( self._payees, indent=4, default=lambda frac: f"{float( frac * 100 ):9.5f}% =~= {frac}" )
        log.info( f"{self._name} Payees: {payees_json}" )

        for i in range( self.erc20s_len()):
            token		= self.erc20s( i )

            # Look up the contract interface we've imported as IERC20Metadata, and use its ABI for
            # accessing any ERC-20 tokens' symbol and decimals.
            IERC20Metadata_key	= self._abi_key( "IERC20Metadata" )
            IERC20Metadata	= self._w3.eth.contract(
                address		= token,
                abi		= self._compiled[IERC20Metadata_key]['abi'],
            )
            # These should be free calls (public data or view-only functions
            self._erc20s[token]	= IERC20Metadata.functions.symbol().call(),IERC20Metadata.functions.decimals().call()

        erc20s_json		= json.dumps( self._erc20s, indent=4 )
        log.info( f"{self._name} ERC-20s: {erc20s_json}" )
