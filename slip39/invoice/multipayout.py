
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

from typing		import Union
from itertools		import count

from web3		import Web3		# noqa F401
from tabulate		import tabulate

from ..util		import remainder_after, fraction_allocated, commas
from ..api		import account
from .ethereum		import Chain, Contract, contract_address  # noqa F401

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


def payout_reserve( addr_frac, bits=16 ):
    """Produce recipients array elements w/ fixed fractional/proportional amounts to predefined
    addresses.  Convert proportions in the range [0,1) totaling to exactly 1.0, to a remainder
    fraction within a multiple of 2^bits, or will raise Exception.  It is not valid to specify
    a recipient with a zero proportion, and the minimum allocation is 1/2^bits.

    The incoming { addr: proportion,... } dict values will be normalized, so any numeric/fractional
    values may be used (eg. arbitrary numeric "shares").

    So long as the final remainder is within +/- 1/scale of 0, its int will be zero, and
    this function will succeed.  Otherwise, it will terminate with a non-zero remainder,
    and will raise an Exception.

    The Gas cost of shifts is 3 (FASTESTSTEP), divisions is 5 (FASTSTEP), so striving to use a scale
    multiplier that is a power of 2 and known at compile-time would be best: eg. a fixed-point
    denominator that is some factor of the bit-size of the numerator.

    Since we're producing fractions in the range (0,1], the fixed-point denominator can be the 2^N
    for an N-bit value supporting the range (0,2^N-1) -- the largest possible fraction we can represent
    will be (2^N-1)/(2^N).  Eg, for a 16-bit value:

        65535/65536 =~= 0.9999847412
            1/65536 =~= 0.0000152588

    """
    addr_frac_sorted		= sorted( addr_frac.items(), key=lambda a_p: a_p[1] )
    addresses,fractions		= zip( *addr_frac_sorted )
    fractions_total		= sum( fractions )
    rem				= None
    for addr,frac,rem in zip(
            addresses,
            fractions,
            remainder_after(
                fractions,
                scale	= 2 ** bits / fractions_total,  # If Fraction, will remain a Fraction
                total	= 2 ** bits,
            )
    ):
        assert frac > 0, \
            f"Encountered a zero proportion: {frac} for recipient {addr}"
        assert int( rem ) < 2 ** bits, \
            f"Encountered a remainder fraction: {rem} numerator greater or equal to the denominator: {2 ** bits}"
        yield addr,frac/fractions_total,rem

    assert rem is not None, \
        "At least one payee is required"
    assert int( rem ) == 0, \
        f"Total payout percentages didn't accumulate to zero remainder: {rem:7.4f} =~= {int( rem )}, for {commas( fractions, final='and' )}"


class MultiPayoutERC20( Contract ):
    """Provide access to our MultiPayoutERC20 Contract; either a pre-existing deployed Contract via
    address, or _deploy a new contract by specifying payees and optionally a list of erc20s to
    support.

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
    def __init__( self, *args, payees=None, erc20s=None, gas=2000000, **kwds ):
        self._erc20s		= dict()		# [ <ERC-20 address>: ("<symbol>",<decimals>), ... ]
        self._payees		= dict()		# { <Payee address>: <Fraction>, ... }
        self._forwarder_hash	= None			# Keccack has of the Forwarder constructor bytecode for CREATE2
        super().__init__( *args, **kwds )
        assert bool( self._address ) ^ bool( payees or erc20s ), \
            "Either a Contract address, or details of desired payees and optionally ERC-20s must be supplied"
        if self._address:
            payees		= self._payees		# recovered payout Fractions
            erc20s		= self._erc20s.keys()

        # Could be deploying a new MultiPayoutERC20 (or just documenting a pre-existing contract's
        # payees).  Computes the Fraction x 2^16 in reserve after each payee, min. 1/2^16.  We start
        # w/ percentages or shares, which may or may not sum to 1.
        payees_frac_total	= sum( payees.values() )
        payees_frac_json	= json.dumps( payees, indent=4, default=lambda frac: f"{float( frac * 100 / payees_frac_total ):9.5f}% =~= {frac}" )
        print( f"Payout Percentages: {payees_frac_json}" )

        # The original proportion assigned to each address is in fracs; the reserve remaining after
        # each payout is in rsvs, and this actual payout percentage vs. recovered payout percentage
        # error is computed later in 'error'.  This may differ from the exact original percentages
        # above, by < 1/2^bits due to fixed point math.  If the payee fractions are recovered from
        # an existing contract, of course these will be exact (no "error").
        bits			= 16
        addrs,fracs,rsvs	= zip( *payout_reserve( payees, bits=bits ))
        payees_reserve		= [ (a,int(r)) for a,r in zip( addrs, rsvs )]

        payees_reserve_json	= json.dumps([
            (a,f"{float( r * 100 / 2**bits ):9.5f}% =~= {r}/{2**bits}" )
            for a,r in payees_reserve
        ], indent=4)
        print( f"Payout Reserve: {payees_reserve_json}" )

        # Now, compute the "error" between the originally specified payout fractions, and the payout
        # fractions recovered after reversing the 1/2^bits reserve calculations.  The error should
        # always be < 1/2^bits.
        addrs,rsvs_int		= zip( *payees_reserve )
        data			= list(
            zip(
                addrs,					# The Payee address
                ( str( payees[a] ) for a in addrs ),    # Original "Share" value specified
                fracs,					# Fraction computed [0,1), full resolution
                rsvs,					# Reserve after payee, full resolution
                rsvs_int,				# Reserve, denominated in 1/2^bits
                fraction_allocated(			# Fraction recovered in 1/2^bits resolution
                    rsvs_int,
                    scale	= 2**bits,
                )
            )
        )
        error			= list(
            (a,s,f"{float(f*100):10.6f}",f"{float(r):10.6f}",ri,f"{float(p*100):10.6f}",f"{(float(p)-float(f))*100:10.6f}")
            for a,s,f,r,ri,p in data
        )
        error_table		= tabulate(
            error,
            headers	= [ 'Payee', 'Share', 'Frac. %', 'Reserve', f"Reserve/2^{bits}",'Frac.Rec. %','Error %' ],
            tablefmt	= 'orgtbl'
        )
        print( f"Payout Error Percentage: \n{error_table}" )

        erc20s_support			= list( erc20s )
        print( f"ERC-20s: {json.dumps( erc20s_support, indent=4, default=str )}" )

        if not self._address:
            self._deploy( payees_reserve, erc20s_support, gas=gas )

    def forwarder_address_precompute(
        self,
        salt: Union[int,bytes,str]
    ):
        """We have all the data required to precompute the CREATE2 ...Forwarder contract address."""
        assert self._forwarder_hash, \
            "Cannot precompute ...Forwarder addresses until MultiPayoutERC20 Contract is deployed and its address is known."
        return contract_address(
            address		= self._address,
            salt		= salt,
            creation_hash	= self._forwarder_hash
        )

    def _update( self ):
        """Query the deployed MultiPayoutERC20 Contract to get payees and the (currently) specified
        ERC-20 tokens (<symbol>, <decimals>).

        Computes the Fraction representing the portion paid to each payee, from the contract's list
        of payees, and the remainder left to subsequent payees.  The Contract enforces that the
        final payee has a 0 reserve.

        TODO: recursively descend into payees that are also MultiPayoutERC20 contracts, and deduce
        the full tree of payees, and their aggregate percentages.

        """
        self._forwarder_hash	= self.forwarder_hash()
        log.info( f"{self._name} Forwarder CREATE2 hash: 0x{self._forwarder_hash.hex()}" )

        def payees_reserves():
            for i in count():
                payee, reserve	= self.payees( i )
                yield payee, reserve
                if not reserve:
                    break

        bits			= 16
        payee,reserve		= zip( *payees_reserves() )
        self._payees		= {
            p: f
            for p, f in zip(
                payee,
                fraction_allocated(
                    reserve,
                    scale	= 2**bits,
                )
            )
        }
        # remaining		= Fraction( 1 )
        # for i in count():
        #     payee, reserve	= self.payees( i )
        #     remaining_after	= remaining * Fraction( reserve, 2 ** 16 )  # TODO: get constant denominator from contract
        #     self._payees[payee]	= remaining - remaining_after
        #     if not reserve:
        #         break  # final payee must have zero reserve
        #     remaining		= remaining_after

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
