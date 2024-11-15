
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

import logging
import textwrap

from typing		import Union
from itertools		import count

from web3		import Web3		# noqa F401

from tabulate		import tabulate

from ..util		import remainder_after, fraction_allocated, commas
from .ethereum		import Chain, Contract, contract_address  # noqa F401

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( 'multipayout' )


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

        >>> from .ethereum import Chain, alchemy_url
        >>> mp = MultiPayoutERC20( Web3.WebsocketProvider( alchemy_url( Chain.Goerli )),
        ...    address		= "0x8b3D24A120BB486c2B7583601E6c0cf37c9A2C04"
        ... )
        MultiPayoutERC20 Payees:
            | Payee                                      | Share                 |   Frac. % |   Reserve |   Reserve/2^16 |   Frac.Rec. % |   Error % |
            |--------------------------------------------+-----------------------+-----------+-----------+----------------+---------------+-----------|
            | 0x7Fc431B8FC8250A992567E3D7Da20EE68C155109 | 4323/65536            |   6.59638 |     61213 |          61213 |       6.59638 |         0 |
            | 0xEeC2b464c2f50706E3364f5893c659edC9E4153A | 1507247699/4294967296 |  35.0933  |     40913 |          40913 |      35.0933  |         0 |
            | 0xE5714055437154E812d451aF86239087E0829fA8 | 2504407469/4294967296 |  58.3103  |         0 |              0 |      58.3103  |         0 |
        ERC-20s:
            | Token                                      | Symbol   |   Digits |
            |--------------------------------------------+----------+----------|
            | 0xe802376580c10fE23F027e1E19Ed9D54d4C9311e | USDT     |        6 |
            | 0xde637d4C445cA2aae8F782FFAc8d2971b93A4998 | USDC     |        6 |
            | 0xaFF4481D10270F50f203E0763e2597776068CBc5 | WEENUS   |       18 |
            | 0x1f9061B953bBa0E36BF50F21876132DcF276fC6e | ZEENUS   |        0 |

        >>> import json
        >>> print( json.dumps( mp._payees, indent=4, default=lambda f: f"{float( f * 100 ):9.5f}%" ))
        {
            "0x7Fc431B8FC8250A992567E3D7Da20EE68C155109": "  6.59637%",
            "0xEeC2b464c2f50706E3364f5893c659edC9E4153A": " 35.09335%",
            "0xE5714055437154E812d451aF86239087E0829fA8": " 58.31028%"
        }
        >>> print( json.dumps( mp._erc20s_data, indent=4 ))
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
    def __init__( self, *args, address=None, payees=None, erc20s=None, gas=2000000, **kwds ):
        """Either connect to an existing Contract by address, or deploy the contract w/ the specified payees
        and (initial) ERC-20s.

        If deploying, produces the _payees_data from the original fractions, and can deduce the
        "error" between the specified fractions and the resultant payout fractions based on
        decimated fixed-point "reserve" values.  If reading from existing deployed contract,
        no error can be calculated as only "reserve" values are available.

        """
        assert bool( address ) ^ bool( payees or erc20s ), \
            "Either a Contract address, or details of desired payees and optionally ERC-20s must be supplied"

        self._payees		= payees or dict()      # { <Payee address>: <Fraction>, ... }
        self._erc20s		= erc20s or list()      # [ <ERC-20 address>: ("<symbol>",<decimals>), ... ]
        self._erc20s_data	= dict()
        self._forwarder_hash	= None			# Keccack has of the Forwarder constructor bytecode for CREATE2
        self._bits		= 16			# reserve values denominated in 1/2^bits

        super().__init__(
            *args, address=address, **kwds		# If address supplied, will invoke self._update()
        )

        if not self._address:
            # Otherwise, will deploy Contract from computed payees reserve values and erc20s list,
            # and then invoke self._update
            self._deploy( self._payees_reserve, self._erc20s, gas=gas )

        print( self )

    def __str__( self ):
        return f"""\
{self.__class__.__name__} Payees:
{textwrap.indent( self._payees_table, ' ' * 4 )}
ERC-20s:
{textwrap.indent( self._erc20s_table, ' ' * 4 )}"""

    @property
    def _erc20s_table( self ):
        return tabulate(
            list(
                (tok,sym,dig)
                for tok,(sym,dig) in self._erc20s_data.items()
            ),
            headers	= [ 'Token', 'Symbol', 'Digits' ],
            tablefmt	= 'orgtbl'
        )

    @property
    def _payees_data( self ):
        """The original proportion assigned to each address is in shares/fractions; the reserve
        remaining after each payout is in rsvs, and this actual payout percentage vs. recovered
        payout percentage error is computed later in 'error'.  This may differ from the exact
        original percentages above, by < 1/2^bits due to fixed point math.  If the payee fractions
        are recovered from an existing contract, of course these will be exact (no "error").

        """
        addrs,fracs,rsrvs	= zip( *payout_reserve( self._payees, bits=self._bits ))
        share			= list( self._payees[a] for a in addrs )
        rsrvs_int		= list( map( int, rsrvs ))
        fracs_recov		= list( fraction_allocated( rsrvs_int, scale=2**self._bits ))
        # Now, compute the "error" between the originally specified payout fractions, and the payout
        # fractions recovered after reversing the 1/2^bits reserve calculations.  The error should
        # always be < 1/2^bits.
        fracs_error		= list( fr - f for f,fr in zip( fracs, fracs_recov ))

        return dict(
            zip(
                addrs,					# The Payee address
                zip(
                    share,				# Original "Share" value specified
                    fracs,				# Fraction computed [0,1), full resolution
                    rsrvs,				# Reserve after each payee, full resolution
                    rsrvs_int,				# Reserve, denominated in 1/2^bits
                    fracs_recov,			# Fraction recovered in 1/2^bits resolution
                    fracs_error,
                )
            )
        )

    @property
    def _payees_reserve( self ):
        return list(
            (a,ri)
            for a,(s,f,r,ri,fr,fe) in self._payees_data.items()
        )

    @_payees_reserve.setter
    def _payees_reserve( self, payees_reserve ):
        """Recovers payee payout fractions from fixed-point (decimated) reserves (eg. obtained from an
        existing contract's data).  If we already have self._payees, just confirms that exactly the same
        reserves are computed!

        This provides a round-trip confirmation of our originally specified payees fractions, to
        decimated reserves and fractions, through contract deployment, and then recovery of
        payees/reserve from the contract, to recomputed decimated fractions.

        """
        addrs,reserve		= zip( *payees_reserve )
        payees			= dict(
            zip(
                addrs,
                fraction_allocated(
                    reserve,
                    scale	= 2**self._bits,
                )
            )
        )
        if self._payees:
            payees_current	= dict(
                (a,fr)
                for a,(s,f,r,ri,fr,fe) in self._payees_data.items()
            )
            if payees != payees_current:
                log.warning( f"Recovered payees fractions don't match: \n{self._payees_table}" )
        else:
            self._payees	= payees

    @property
    def _payees_table( self ):
        return tabulate(
            list(
                (a,f"{s}",f"{float(f*100):10.6f}",f"{float(r):10.6f}",ri,f"{float(fr*100):10.6f}",f"{float(fe*100):10.6f}")
                for a,(s,f,r,ri,fr,fe) in self._payees_data.items()
            ),
            headers	= [ 'Payee', 'Share', 'Frac. %', 'Reserve', f"Reserve/2^{self._bits}",'Frac.Rec. %','Error %' ],
            tablefmt	= 'orgtbl'
        )

    def _forwarder_address_precompute(
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

        def payees_reserve():
            for i in count():
                payee, reserve	= self.payees( i )
                yield payee, reserve
                if not reserve:
                    break

        # This only *needs* to be done at initial _update from an existing deployed contract.
        # However, we'll always recover them here (even if we just deployed the contract), to
        # make certain our reverse Reserve to Fraction calculation is correct.  Computes
        # self._payees if absent.
        self._payees_reserve	= list( payees_reserve() )

        def erc20s_data():
            # Look up the contract interface we've imported as IERC20Metadata, and use its ABI
            # for accessing any ERC-20 tokens' symbol and decimals.
            IERC20_key		= self._abi_key( "IERC20Metadata" )
            for i in range( self.erc20s_len()):
                tok		= self.erc20s( i )
                IERC20_tok	= self._w3.eth.contract(
                    address	= tok,
                    abi		= self._compiled[IERC20_key]['abi'],
                )
                # These should be free calls (public data or view-only functions)
                sym			= IERC20_tok.functions.symbol().call()
                dig			= IERC20_tok.functions.decimals().call()
                yield tok,(sym,dig)

        self._erc20s_data	= dict( erc20s_data() )
        erc20s			= list( self._erc20s_data )
        if self._erc20s:
            assert self._erc20s == erc20s
        else:
            self._erc20s	= erc20s
