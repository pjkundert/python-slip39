
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
from __future__          import annotations

import logging
import math

from dataclasses	import dataclass
from collections	import defaultdict
from typing		import Dict, Union, Optional, Sequence, List, Any, Tuple
from fractions		import Fraction
from pathlib		import Path
from datetime		import datetime, timedelta, timezone
from calendar		import monthrange

import fpdf
import tabulate

from crypto_licensing.misc import get_localzone, Duration

from ..api		import Account
from ..util		import commas, is_listlike, is_mapping
from ..defaults		import (
    INVOICE_CURRENCY, INVOICE_ROWS, INVOICE_STRFTIME, INVOICE_DUE, INVOICE_DESCRIPTION_MAX,
    INVOICE_FORMAT, MM_IN, FILENAME_FORMAT, COLOR,
)
from ..layout		import Region, Text, Image, Box, Coordinate, layout_pdf
from .ethereum		import tokeninfo, tokenprices, tokenknown

"""
Invoice artifacts:

    Invoice/Quote	-- States deliverables, prices/taxes, and totals in various currencies

    Receipt		-- The Invoice, marked "PAID"

"""
log				= logging.getLogger( "artifact" )

# Custom tabulate format that provides "====" SEPARATING_LINE between line-items and totals
tabulate._table_formats["totalize"] = tabulate.TableFormat(
    lineabove		= tabulate.Line("", "-", "  ", ""),
    linebelowheader	= tabulate.Line("", "-", "  ", ""),
    linebetweenrows	= tabulate.Line("", "=", "  ", ""),
    linebelow		= tabulate.Line("", "-", "  ", ""),
    headerrow		= tabulate.DataRow("", "  ", ""),
    datarow		= tabulate.DataRow("", "  ", ""),
    padding		= 0,
    with_header_hide	= ["lineabove", "linebelow", "linebetweenrows"],
)
tabulate.multiline_formats["totalize"]	= "totalize"


def tabulate_nopad( *args, **kwds ):
    """Removes the default 2-character tabulate.MIN_PADDING from around column headers."""
    try:
        min_padding	= tabulate.MIN_PADDING
        tabulate.MIN_PADDING = 0
        return tabulate.tabulate( *args, **kwds )
    finally:
        tabulate.MIN_PADDING = min_padding


# An invoice line-Item contains the details of a component of a transaction.  It is priced in a
# currency, with a number of 'units', and a 'price' per unit.
#
# The 'tax' is a proportion of the computed total amount allocated to taxation; if <1 (eg. 0.05 or
# 5%), then it is added to the total amount; if > 1 (eg. 1.05 or 5%), then the prices is assumed to
# be tax-inclusive and it is subtracted from the computed amount.
#
# Each line-Item may be expressed in a different currency.
@dataclass
class Item:
    description: str				# "Widgets for The Thing"
    price: Union[int,float,Fraction]		# 1.98 eg. $USDC, Fraction( 10000, 12 ) * 10**9, eg. ETH Gwei per dozen, in Wei
    units: Union[int,float]	= 1		# 198, 1.5
    tax: Optional[float,Fraction] = None        # 0.05, Fraction( 5, 100 ) eg. GST, added to amount, 1.05 GST, included in amount
    decimals: Optional[int]	= None		# Number of decimals to display computed amounts, eg. 2.; default is 1/3 of token decimals
    currency: Optional[str]	= None		# Default: $USD (value proxy is USDC)


class LineItem( Item ):
    def net( self ):
        """Computes the LineItem total 'amount', the 'taxes', and info on tax charged.  Use the
        full-precision percentage, to support fractional tax percentages.

        Uses the default Invoice Currency if none specified.

        """
        amount			= self.units * self.price
        taxes			= 0
        taxinf			= 'no tax'
        if self.tax:
            if self.tax < 1:
                taxinf		= f"{float( self.tax * 100 ):g}% add"
                taxes		= amount * self.tax
                amount	       += taxes
            elif self.tax > 1:
                taxinf		= f"{float(( self.tax - 1 ) * 100 ):g}% inc"
                taxes		= amount - amount / self.tax
        return amount, taxes, taxinf  # denominated in self.currencies


def conversions_table( conversions, symbols=None, greater=None, tablefmt=None, precision=None ):
    """Output a tabulation of conversion ratios, optionally >= a value (or of a pair of ratios), to
    the specified precision (default, 8 decimal points).

    Sort by the column with the highest density of conversion ratios.

    """
    if symbols is None:
        symbols			= sorted( set( sum( conversions.keys(), () )))
    if greater is None:
        greater			= .001
    if precision is None:
        precision		= 8
    symbols			= list( symbols )

    # The columns are typed according to the least generic type that *all* rows are convertible
    # into.  So, if any row is a string, it'll cause the entire column to be formatted as strings.
    def fmt( v, d ):
        if v:
            return round( v, d )
        return v

    headers_raw			= [ 'Coin' ] + [ f"in {s}" for s in symbols ]
    convers_raw			= [
        [ r ] + list(
            (
                '' if r == c or (r,c) not in conversions
                else '' if ( greater and conversions.get( (r,c) ) and conversions.get( (c,r) )
                             and ( conversions[r,c] < ( greater if isinstance( greater, (float,int) ) else conversions[c,r] )))
                else fmt( conversions[r,c], 8 )   # ie. to the Sat (1/10^8 Bitcoin)
            )
            for c in symbols
        )
        for r in symbols
    ]
    # Now, remove any column that are completely blank ('', not None).  This will take place for
    # worthless (or very low valued) currencies, esp. w/ a small 'greater'.  Transpose the
    # conversions (so each column is a row), and elide any w/ empty conversions rows.  Finally,
    # re-transpose back to columns.
    convers_txp			= list( zip( *convers_raw ))
    headers_use,convers_use_txp	= zip( *sorted(
        [
            (hdr,col)
            for hdr,col in zip( headers_raw, convers_txp )
            if any( c != '' for c in col )
        ],
        key	= lambda hdr_col: sum( map( bool, hdr_col[1] )),  	# number of occupied entries in column
        reverse	= True,
    ))
    # Finally sort by the 2nd (first non-label) column, which has the most occupied values; consider None/'' entries as zero
    convers_use			= sorted(
        zip( *convers_use_txp ),
        key	= lambda row: row[1] or 0,				# by 1st numeric column's conversion ratio
        reverse	= True,
    )

    return tabulate_nopad(
        convers_use,
        headers		= headers_use,
        floatfmt	= f',.{precision}g',
        intfmt		= ',',
        missingval	= '?',
        tablefmt	= tablefmt or INVOICE_FORMAT,
    )


class ConversionError( Exception ):
    pass


def conversions_remaining( conversions, verify=None ):
    """Complete the graph of conversion ratios, if we have a path from one pair to another.  Returns
    falsey if no additional conversion ratios were computable; truthy if some *might* be possible.
    Each run looks for single-hop conversions available.

    Put any desired conversions (eg. DOGE/USD) into conversions w/ None as value.

    For example, if ETH/USD: 1234.56 and BTC/USD: 23456.78, then we can deduce BTC/ETH:
    19.0001134007 and ETH/BTC: 0.05263126482.  Then, on the next call, we could compute DOGE/USD ==
    0.090308 if we provide BTC/DOGE: 3.85e-6

    Updates the supplied { ('a','b'): <ratio>, ...} dict, in-place.

    If NO None values remain after all computable ratios are deduced, returns False, meaning "no
    remaining unresolved conversions".

    Otherwise, return None iff we couldn't deduce any more conversion ratios, but there remain some
    unresolved { (a,b): None, ...} in conversions.

    """
    updated			= False
    # First, take care of any directly available one-hop conversions.
    for (a,b),r in list( conversions.items() ):
        if r and conversions.get( (b,a) ) is None:
            conversions[b,a]	= 1/r
            log.info( f"Deduced  {b:>6}/{a:<6} = {float( 1/r ):13.6f} from {a:>6}/{b:<6} == {float( r ):13.6f} == {r}" )
            updated		= True
        if r is None:
            continue
        for (a2,b2),r2 in list( conversions.items() ):
            if r2 is None:
                continue
            if b == b2 and a != a2 and conversions.get( (a,a2) ) is None:
                if r == r2:
                    # A special case for zero-valued (or other identically valued) tokens: the ratio is 1
                    # Eg. ZEENUS/ETH=0/1 / WEENUS/ETH=0/1 --> ZEENUS/WEENUS=1/1
                    conversions[a,a2] = 1
                    log.info( f"Unity    {a:>6}/{a2:<6} = {float( conversions[a,a2] ):13.6f} from {a:>6}/{b:<6} == {float( r ):13.6f} / {a2:>6}/{b2:<6} == {float( r2 ):13.6f}" )
                    updated	= True
                elif r2:
                    # Eg. USD/BTC=25000/1 / DOGE/BTC=275000/1 --> USD/DOGE=1/4
                    conversions[a,a2] = r / r2
                    log.info( f"Divide   {a:>6}/{a2:<6} = {float( conversions[a,a2] ):13.6f} from {a:>6}/{b:<6} == {float( r ):13.6f} / {a2:>6}/{b2:<6} == {float( r2 ):13.6f}" )
                    updated	= True
            if b == a2 and a != b2 and conversions.get( (a,b2) ) is None:
                # Eg. USD/BTC=25000/1 * BTC/DOGE=1/275000 --> USD/DOGE=1/4
                conversions[a,b2] = r * r2
                log.info( f"Multiply {a:>6}/{b2:<6} = {float( conversions[a,b2] ):13.6f} from {a:>6}/{b:<6} == {float( r ):13.6f} x {a2:>6}/{b2:<6} == {float( r2 ):13.6f}" )
                updated		= True
    if updated:
        return True
    # OK, got all available a/b --> b/a and a/b * b/c --> a/c and a/b / c/b --> a/c.  See if we
    # can find any routes between the desired a/b pairs.
    for (a,b),r in conversions.items():
        if r is not None:
            continue
        for c2,r2 in conversions.items():
            if r2 and a in c2:
                for c3,r3 in conversions.items():
                    if c2 != c3 and r3 and b in c3 and ( x_s := set( c2 ).intersection( set( c3 ))):
                        # We want a/b and we have found a/x or x/a, and b/x or x/b.  Assume their
                        # inverse is in conversions, and is (also) non-zero.
                        log.warning( f"Found intersection between {c2!r} and {c3!r}: {x_s!r}" )
                        x,	= x_s
                        conversions[a,b] = conversions[a,x] * conversions[b,x]
                        log.info( f"Compute  {a:>6}/{b2:<6} = {float( conversions[a,b] )} from {a:>6}/{x:<6} == {float( conversions[a,x] ):13.6f} and {b:>6}/{x:<6} == {float( conversions[b,x] ):13.6f}" )
                        conversions[b,a] = 1 / conversions[a,b]
                        return True

    # No more currency pairs are deducible from our present data; If no more are desired (contain
    # None), then we can return falsey (we're done), otherwise, raise an Exception or return truthy:
    # a description of what pairs remain undefined.
    remains			= commas( sorted( f'{a}/{b}' for (a,b),r in conversions.items() if r is None ), final='and' )
    if not remains:
        return False
    resolved			= commas( sorted( f'{a}/{b}' for (a,b),r in conversions.items() if r and r > 1 ), final='and' )
    msg				= f"Failed to find ratio(s) for {remains} via {resolved}"
    if verify:
        raise ConversionError( msg )
    log.debug( msg )
    return msg


def cryptocurrency_symbol( name, chain=None, w3_url=None, use_provider=None ):
    try:
        return Account.supported( name )
    except ValueError as exc:
        log.info( f"Could not identify currency {name!r} as a supported Cryptocurrency: {exc}" )
    # Not a known core Cryptocurrency; a Token?
    try:
        return tokeninfo( name, w3_url=w3_url, use_provider=use_provider ).symbol
    except Exception as exc:
        log.warning( f"Failed to identify currency {name!r} as an ERC-20 Token: {exc}" )
        raise


def cryptocurrency_proxy( name, decimals=None, chain=None, w3_url=None, use_provider=None ):
    """Return the named ERC-20 Token (or a known "Proxy" token, eg. BTC -> WBTC).  If not a
    Token/Proxy, then return any known Cryptocurrency matching the name.  In this case, the
    caller must (typically) already be informed of the currency value of such a Cryptocurrency by
    other means.

    """
    try:
        return tokeninfo( name, w3_url=w3_url, use_provider=use_provider )
    except Exception as exc:
        log.info( f"Could not identify currency {name!r} as an ERC-20 Token: {exc}" )
    # Not a known Token; a core known Cryptocurrency?
    return tokenknown( name, decimals=decimals )


class Invoice:
    """The totals for some invoice line items, in terms of some currencies, payable into some
    Cryptocurrency accounts.

    - Each account's native cryptocurrency symbol (at least) is reflected in computed invoice totals.
      - Eg. if ETH, BTC, XRP and DOGE Accounts are provided, we'll totalize into all 4.
    - Each currency must correspond to one cryptocurrency account (eg. Ethereum ERC-20s --> ETH account)
      - Eg. "US Dollar" (USDC) or "Wrapper Bitcoin" (WBTC) --> ETH, "Bitcoin" or BTC --> BTC
    - Each currency can either be supplied a ratio in conversions, or have a "Proxy" Token for an Oracle
      - Eg. "BTC" --> WBTC Token, "XRP" --> conversions[('XRP','BTC'): 0.00001797

    Currencies may be supplied as a recognized slip39.Account.supported( <name> ); full lower-case
    names in Account.CRYPTO_NAMES.keys(), upper-case symbols in Account.CRYPTO_NAMES.values().  For
    all other than BTC and ETH, a conversion ratio to some common currency (eg. USD) must be
    supplied in conversions.

    Otherwise, a ERC-20 token contract address or a token's symbol or full name (for known
    cryptocurrencies eg. "BTC", "ETH", or some known ERC-20 tokens (~top 100).  Presently, we only
    support obtaining price ratios for invoice cryptocurrencies that have a highly-liquid Ethereum
    ERC-20 "proxy", eg. ETH(WETH), BTC(WBTC).

    Can emit the line items in groups with summary sub-totals and a final total.

    Reframes the price of each line in terms of the Invoice's currencies (default: USD), providing
    "Total <SYMBOL>" and "Taxes <SYMBOL>" for each Cryptocurrency symbols.  NOTE: These are a
    *running* Total; the LineItem Amount is each line's total, in terms of that line's currency.

    Now that we have Web3 details, we can query tokeninfos and hence format currency decimals
    correctly.

    """
    def __init__(
        self, lines,
        accounts: Sequence[Account],		 # [ <Account>, ... ]   .crypto is symbol, eg. BTC, ETH, XRP
        currencies: Optional[List]	= None,	 # "USD" | [ "USD", "BTC" ] (first-most currencies/accounts is conversion "reference" currency)
        conversions: Optional[Dict]	= None,  # { ("USD","ETH"): 1234.56, ("USD","BTC"): 23456.78, ...}
        w3_url			= None,
        use_provider		= None,
    ):
        self.lines		= list( lines )
        self.w3_url		= w3_url
        self.use_provider	= use_provider

        # Collect all desired Invoice currencies; named, and those associated with supplied
        # accounts.  These are symbols, names, or ERC-20 token addresses.  Some may translate
        # into things we can get prices for via an off-chain Oracle via the Ethereum blockchain,
        # but some may not -- these must be supplied w/ a ratio in conversions, to at least one
        # token we *do* have the ability to get the value of.  This requires the caller to have
        # some kind of price feed or oracle of their own; it is recommended to use the 1inch
        # OffchainOracle instead, by sticking to the main Cryptocurrencies for which we have
        # real-time price proxies, eg. USD(USDC), BTC(WBTC), ETH(WETH).  If None (supplied or in
        # sequence), replace with default INVOICE_CURRENCY.
        if isinstance( currencies, (str, type(None)) ):
            currencies		= [ currencies ]
        currencies		= set( currencies )
        if None in currencies:
            currencies.remove( None )
            currencies.add( INVOICE_CURRENCY )
        log.info( f"Found {len( currencies )} Invoice currencies: {commas( currencies, final='and')}" )

        # Convert all known Crypto-currencies or Tokens to symbols (all upper-case).  Any
        # unrecognized as known Cryptos or Tokens will raise an Exception.  This effectively de-dups
        # all accounts/currencies, but doesn't substitute know "proxy" tokens (eg. BTC <-> WBTC)
        currencies		= set(
            cryptocurrency_symbol( c, w3_url=w3_url, use_provider=use_provider )
            for c in currencies
        )
        log.info( f"Found {len( currencies )} Invoice currency symbols: {commas( currencies, final='and')}" )

        # Associate any Crypto accounts provided w/ their core cryptos (adding any new ones from
        # accounts, to self.currencies).  After this every Invoice currency symbol is in
        # currencies_account.keys(), and every one with a provided account address is in
        # currencies_account[symbol]
        currencies_account	= { c: None for c in currencies }
        if accounts:
            for a in accounts:
                assert currencies_account.get( a.symbol ) is None, \
                    f"Duplicate accounts given for {a.symbol}: {a.address} vs. {currencies_account[a.symbol]}"
                currencies_account[a.symbol] = a
        currencies		= set( currencies_account )
        log.info( f"Found {len( currencies )} Invoice currency symbols + accounts: {commas( currencies, final='and')}" )

        # Associate any Crypto/Tokens w/ available ERC-20 proxies (eg. BTC -> WBTC), and any ERC-20s
        # w/ any supplied ETH account (eg.USDC, WBTC --> <ETH account>) Thus, if BTC was selected
        # and an Ethereum account provided, the buyer can pay in BTC to the Bitcoin account, or in
        # ETH or WBTC to the Ethereum account.  This will add the symbols for all Crypto proxies to
        # currencies_account.
        currencies_alias	= {}  # eg. { "WBTC": TokenInfo( "BTC", ... ), ... }
        currencies_proxy	= {}  # eg. { "BTC": TokenInfo( "WBTC", ... ), ... }
        for c in currencies:
            try:
                currencies_proxy[c] = alias = tokeninfo( c, w3_url=w3_url, use_provider=use_provider )
            except Exception as exc:
                # May fail later, if no conversions provided for this currency
                log.info( f"Failed to find proxy for Invoice currency {c}: {exc}" )
            else:
                # Yup; a proxy for a Crypto eg. BTC -> WBTC was found, or a native ERC-20 eg. USDC
                # was found; associate it with any ETH account provided.
                if eth := currencies_account.get( 'ETH' ):
                    currencies_account[currencies_proxy[c].symbol] = eth
                try:
                    known	= tokenknown( c )
                except Exception:
                    pass
                else:
                    # Aliases; of course, the native symbol is included in known aliases
                    currencies_alias[alias.symbol] = known
                    currencies_alias[known.symbol] = known
                    log.info( f"Currency {c}'s Proxy Symbol {alias.symbol} is an alias for {known.symbol}" )
        log.info( f"Found {len( currencies_proxy )} Invoice currency proxies: {commas( ( f'{c}: {p.symbol}' for c,p in currencies_proxy.items() ), final='and')}" )
        log.info( f"Added {len( set( currencies_account ) - currencies )} proxies: {commas( set( currencies_account ) - currencies, final='and' )}" )
        log.info( f"Alias {len( currencies_alias )} symbols to their native Crytocurrencies: {commas( ( f'{a}: {c.symbol}' for a,c in currencies_alias.items() ), final='and')}" )
        currencies		= set( currencies_account )

        # Find all LineItem.currency -> Invoice.currencies conversions required.  This
        # establishes the baseline conversions ratio requirements to convert LineItems to each
        # Invoice currency.  No prices are yet found.  Also, ensure that there is a route to
        # deduce the price of every provided cryptocurrency conversion.  For example, if the
        # invoice payment currency is XRP, and we have been provided the {('XRP','BTC'):
        # <ratio>}, how do we convert from every other currency to XRP?  It must occur via BTC.
        # Therefore, we must require a conversion from each currency found to a core currency; in
        # our case, ETH (since it is the default conversion ratio currency for our Ethereum
        # Oracle).
        line_currencies		= set(
            line.currency or INVOICE_CURRENCY
            for line in self.lines
        )
        # Finally, add all remaining Invoice and LineItem cryptocurrencies to currencies_proxy, by
        # their original names, symbols and names.  Now, every Invoice and LineItem currency (by
        # name and alias) is represented in currencies_proxy.
        for lc in line_currencies | currencies:
            proxy		= cryptocurrency_proxy( lc, w3_url=w3_url, use_provider=use_provider )
            for alias in set( (lc, proxy.name, proxy.symbol) ):
                if alias in currencies_proxy:
                    assert currencies_proxy[alias] == proxy, \
                        f"Incompatible LineItem.currency {lc!r} w/ currency {alias!r}: \n{proxy} != {currencies_proxy[alias]}"
                currencies_proxy[alias] = proxy
        log.info( f"Found {len( currencies_proxy )} Invoice and LineItem currencies: {commas( ( f'{n}: {p.symbol}' for n,p in currencies_proxy.items() ), final='and')}" )

        line_symbols		= set(
            cryptocurrency_symbol( lc )
            for lc in line_currencies
        )
        log.info( f"Found {len( line_symbols )} LineItem currencies: {commas( line_symbols, final='and')}" )

        # Now that we have all line-item, invoice and account Cryptocurrency symbols, we can
        # identify all the conversion we require to satisfy the Invoice.  Every LineItem
        # Cryptocurrency symbol must be convertible to each Invoice Cryptocurrency symbol.
        if conversions is None:
            conversions		= {}
        for ls in line_symbols:
            for c in currencies:
                if ls != c:
                    conversions.setdefault( (ls,c), None )  # eg. ('USDC','BTC'): None

        self.accounts		= accounts
        self.currencies		= currencies		# { "USDC", "BTC", ... }
        self.currencies_account	= currencies_account    # { "USDC": "0xaBc...12D", "BTC": "bc1...", ... }
        self.currencies_proxy	= currencies_proxy      # { "BTC": TokenInfo( "WBTC", ... ), ... }
        self.currencies_alias	= currencies_alias      # { "WBTC": TokenInfo( "BTC", ... ), ... }
        self.conversions	= conversions		# { ("BTC","ETH"): 14.3914, ... }
        self.created		= datetime.utcnow().astimezone( timezone.utc )
        self.resolved		= self.created

    def unsatisfied( self ):
        return set(
            sum(
                (
                    pair
                    for pair,ratio in self.conversions.items()
                    if ratio is None
                ),
                ()
            )
        ) - { 'ETH' }

    def resolve( self ):
        unsatisfied		= self.unsatisfied()
        if not unsatisfied:
            return

        for c in unsatisfied:
            if (c,'ETH') not in self.conversions:
                log.info( f"Require {c:>6}/ETH conversion ratio" )
                self.conversions[c,'ETH'] = None

        # Resolve all resolvable conversions (ie. from any supplied), see what's left
        while ( remaining := conversions_remaining( self.conversions ) ) and not isinstance( remaining, str ):
            if log.isEnabledFor( logging.DEBUG ):
                log.debug( f"Working: \n{conversions_table( self.conversions, greater=False )}" )
        log.info( f"{'Remaining' if remaining else 'Resolved'}:\n{conversions_table( self.conversions, greater=False )}\n{f'==> {remaining}' if remaining else ''}" )

        while remaining:
            # There are unresolved LineItem -> Invoice currencies.  We need to get a price ratio between
            # the LineItem currency, and at least one of the main Invoice currencies.  Since we know we're dealing
            # in Ethereum ERC-20 proxies, we'll keep getting ratios between currencies and ETH (the
            # default from tokenprices).
            candidates		= self.unsatisfied()
            for c in candidates:
                try:
                    (one,two,ratio), = tokenprices( c, w3_url=self.w3_url, use_provider=self.use_provider )
                except Exception as exc:
                    log.info( f"Ignoring candidate {c} for price deduction: {exc}" )
                    continue
                if self.conversions.get( (c,two.symbol) ) is None or self.conversions.get( (one.symbol,two.symbol) ) is None:
                    if self.conversions.get( (c,two.symbol) ) is None:
                        log.info( f"Updated  {c:>6}/{two.symbol:<6} to: {ratio}" )
                        self.conversions[c,two.symbol] = ratio
                    if self.conversions.get( (one.symbol,two.symbol) ) is None:
                        log.info( f"Updated  {one.symbol:>6}/{two.symbol:<6} to: {ratio}" )
                        self.conversions[one.symbol,two.symbol] = ratio
                    break
            else:
                # We must reject any zero-valued Cryptocurrencies from target currencies!  If the
                # caller selects eg. WEENUS as a payment currency, and we allow it, it might result
                # in an "infinite" payment in a zero-valued currency as a payment option.  We can
                # detect this, right here, because we won't be able to compute any conversion
                # ratio between a valuable cryptocurrency, and a zero-valued cryptocurrency.
                # Instead failing, remove it as a payment option!
                raise ConversionError( f"Failed to resolve conversion ratios {remaining}, using {len( candidates )} remaining candidates {commas( candidates, final='and' )}" )
            while ( remaining := conversions_remaining( self.conversions ) ) and not isinstance( remaining, str ):
                if log.isEnabledFor( logging.DEBUG ):
                    log.debug( f"Working: \n{conversions_table( self.conversions, greater=False )}" )
            log.info( f"{'Remaining' if remaining else 'Resolved'}:\n{conversions_table( self.conversions, greater=False )}\n{f'==> {remaining}' if remaining else ''}" )
        self.resolved		= datetime.utcnow().astimezone( timezone.utc )

    def decimals( self, currency ):
        info			= self.currencies_proxy[currency]
        if info.symbol in self.currencies_alias:
            info		= self.currencies_alias[info.symbol]
        return info.decimals

    def headers( self ):
        """Output the headers to use in tabular formatting of iterator.  By default, we'd recommend hiding any starting
        with an _ prefix (this is the default).

        Beware of making column labels w/ spaces; the 2nd half of some column labels is assumed to
        be a Cryptocurrency symbol for formatting purposes.

        """
        return (
            '_#',
            'Description',
            'Qty',
            'Price',
            '_Tax',
            'Tax%',
            'Taxes',
            '_Net',
            'Amount',
            '_Currency',
            'Coin',
            '_Decimals',
            '_Token',
        ) + tuple(
            f"_Total {currency}"
            for currency in sorted( self.currencies )
        ) + tuple(
            f"_Taxes {currency}"
            for currency in sorted( self.currencies )
        )

    def __iter__( self ):
        """Iterate of lines, computing totals in each Invoice.currencies

        Note that numeric values may be int, float or Fraction, and these are retained through
        normal mathematical operations, at full available precision (even if this is beyond the
        "decimals" precision of the underlying cryptocurrency).

        The number of decimals desired for each line is provided in "_Decimals".  The native
        number of decimals must be respected in this line's calculations.  For example, if eg.  a
        0-decimals Token is used, the Net, Tax and Amount are rounded to 0 decimals.  All
        rounding/display decimals should be performed at the final display of the data.

        The sums in various currencies converted from each line are not rounded; the currency
        ratio and hence sum is full precision, and is only rounded at the final use.

        """

        self.resolve()  # Resolve any yet unresolved conversions.  May raise Exception, if unresolvable.

        tot			= {
            c: 0. for c in self.currencies
        }
        tax			= {
            c: 0. for c in self.currencies
        }

        for i,line in enumerate( self.lines ):
            line_amount,line_taxes,line_taxinf = line.net()
            line_net		= line_amount - line_taxes
            # The line's ERC-20 Token (or a known proxy for the named Cryptocurrency), or a
            # TokenInfo for the specified known Cryptocurrency.  Always displays the underlying
            # native Cryptocurrency symbol (if known), even if a "Proxy" is specified, or used
            # for pricing.
            line_currency	= line.currency or INVOICE_CURRENCY  # Eg. "Bitcoin", "WBTC", "BTC"
            line_curr		= self.currencies_proxy[line_currency]
            log.info( f"Line currency {line_currency} has proxy {line_curr.symbol:6}: decimals: {line_curr.decimals}" )
            if line_curr.symbol in self.currencies_alias:
                line_curr	= self.currencies_alias[line_curr.symbol]
                log.info( f"Line currency {line_currency} alias for {line_curr.symbol:6}: decimals: {line_curr.decimals}" )
            line_symbol		= line_curr.symbol
            line_decimals	= line.decimals
            if line_decimals is None:
                line_decimals	= line_curr.decimals // 3

            for c in self.currencies:
                if line_curr.symbol == c:
                    tot[c]     += line_amount
                    tax[c]     += line_taxes
                else:
                    tot[c]     += line_amount * self.conversions[line_curr.symbol,c]
                    tax[c]     += line_taxes  * self.conversions[line_curr.symbol,c]
            yield (
                i,			# The LineItem #, and...
                line.description,
                line.units,
                line.price,
                line.tax,
                line_taxinf,
                line_taxes,
                line_net,
                line_amount,
                line_currency,		# the line's currency
                line_symbol,		# and Token symbol
                line_decimals,		# the desired number of decimals
                line_curr,		# and the associated tokeninfo
            ) + tuple(
                tot[c] for c in sorted( self.currencies )
            ) + tuple(
                tax[c] for c in sorted( self.currencies )
            )

    def pages(
        self,
        page		= None,
        rows		= None,
    ):
        """Yields a sequence of lists containing rows, paginated into 'rows' chunks.

        If page (zero-basis) specified, only yields matching pages.

        By default, we'll assume we need about 1/2 the rows for non-line-item invoice details
        (metadata, totals, conversions, ...)

        """
        if rows is None:
            rows		= INVOICE_ROWS // 2

        def page_match( i ):
            if page is None:
                return True
            if hasattr( page, '__contains__' ):
                return i in page
            return i == page

        page_i,page_l		= 0,[]
        for row in iter( self ):
            page_l.append( row )
            if len( page_l ) >= rows:
                if page_match( page_i ):
                    yield page_l
                page_i,page_l	= page_i+1,[]
        if page_l and page_match( page_i ):
            yield page_l

    def tables(
        self, *args,
        tablefmt	= None,
        columns		= None,		# list (ordered) set/predicate (unordered)
        totalfmt	= None,
        totalize	= None,		# Final page includes totalization
        description_max	= None,		# Default to some reasonable max
        **kwds				# page, rows, ...
    ):
        """Tabulate columns into textual tables.  Each page yields 3 items:

            <page>,<line-items>,<sub-totals>,<totals>

        The sub-totals are per-page; the totals are running totals of all pages produced thus far;
        hence the last page's totals are the full invoice totals.

        The 'columns' is a filter (a set/list/tuple or a predicate) that selects the columns
        desired; by default, elides any columns having names starting with '_'.  We will accept
        matches case-insensively, and ignoring any leading/trailing '_'.

        If any columns w/ leading '_' *are* selection, we trim the '_' for display.

        """
        if totalize is None:
            totalize		= True

        headers			= self.headers()

        def can( c ):
            """Canonicalize a header/column name for comparison"""
            return c.strip( '_' ).lower()

        headers_can		= [ can( h ) for h in headers ]
        if columns:
            if is_listlike( columns ):
                try:
                    selected	= tuple( headers_can.index( can( c )) for c in columns )
                except ValueError as exc:
                    raise ValueError( f"Columns not found: {commas( c for c in columns if can( c ) not in headers_can )}" ) from exc
            elif hasattr( columns, '__contains__' ):
                selected	= tuple( i for i,h in enumerate( headers ) if can( h ) in [ can( c ) for c in columns ] )
                assert selected, \
                    "No columns matched"
            else:
                # User-provided column predicate; do not canonicalize
                selected	= tuple( i for i,h in enumerate( headers ) if columns( h ) )
        else:
            # Default; just ignore _... columns
            selected		= tuple( i for i,h in enumerate( headers ) if not h.startswith( '_' ) )
        headers_selected	= tuple( headers[i] for i in selected )

        log.info( f"Tabulating indices {commas(selected, final='and')}: {commas( headers_selected, final='and' )}" )
        pages			= list( self.pages( *args, **kwds ))

        # Overall formatted decimals for the entire invoice; use the greatest desired decimals of
        # any token/line, based on Cryptocurrency proxies.  Individual line items may have been
        # rounded to lower decimals.
        #decimals_i		= headers_can.index( can( '_Decimals' ))
        #decimals		= max( line[decimals_i] for page in pages for line in page )
        #floatfmt		= ',f'  # f',.{decimals}f'
        #intfmt			= ','
        page_prev		= None
        for p,page in enumerate( pages ):
            first		= page_prev is None
            final		= p + 1 == len( pages )

            # {Sub}total for payment cryptocurrrencies are rounded to the individual
            # Cryptocurrency's designated decimals // 3.  For typical ERC-20 tokens, this is
            # eg. USDC: 6 // 3 == 2, WBTC: 18 // 3 == 6.  For known Cryptocurrencies, eg. BTC: 24 //
            # 3 == 8.
            #
            # If a symbol is a "proxy" token for some upstream known cryptocurrency, then the
            # upstream native cryptocurrency's decimals should be used, so that all lines match.  We
            # keep track of each cryptocurrency_alias[<proxy-symbol>] -> <original-symbol>
            #
            # TODO: There should be a more sensible / less brittle way to do this.
            def deci( c ):
                return self.decimals( c ) // 3

            def toti( c ):
                return headers_can.index( can( f'_Total {c}' ))

            def taxi( c ):
                return headers_can.index( can( f'_Taxes {c}' ))

            # The per-currency Sub-totals (for each page), sorted in ascending order.  Stabilizes
            # the sort by also sorting the currencies.
            subtotal_rows	= sorted(
                [
                    [
                        str( self.currencies_account[c] ),
                        round( page[-1][taxi( c )], deci( c )) if first else round( page[-1][taxi( c )] - page_prev[-1][taxi( c )], deci( c )),
                        round( page[-1][toti( c )], deci( c )) if first else round( page[-1][toti( c )] - page_prev[-1][toti( c )], deci( c )),
                        c,
                        self.currencies_account[c].name if c == self.currencies_account[c].symbol else self.currencies_proxy[c].name,
                    ]
                    for c in sorted( self.currencies )
                ],
                key	= lambda r: r[2]
            )
            subtotal_headers	= (
                'Account',
                'Taxes' if final else f'Taxes {p+1}/{len( pages )}',
                'Subtotal' if final else f'Subtotal {p+1}/{len( pages )}',
                'Coin',
                'Currency',
            )
            subtotal		= tabulate_nopad(
                subtotal_rows,
                headers		= subtotal_headers,
                intfmt		= ',',
                floatfmt	= ',.15g',
                tablefmt	= tablefmt or INVOICE_FORMAT,
            )

            # And the per-currency Totals (up to current page)
            total_rows		= sorted(
                [
                    [
                        str( self.currencies_account[c] ),
                        round( page[-1][taxi( c )], deci( c )),
                        round( page[-1][toti( c )], deci( c )),
                        c,
                        self.currencies_account[c].name if c == self.currencies_account[c].symbol else self.currencies_proxy[c].name,
                    ]
                    for c in sorted( self.currencies )
                ],
                key	= lambda r: r[2]
            )
            total_headers	= (
                'Account',
                'Taxes' if final else f'Taxes {p+1}/{len( pages )}',
                'Total' if final else f'Total {p+1}/{len( pages )}',
                'Coin',
                'Currency',
            )
            total		= tabulate_nopad(
                total_rows,
                headers		= total_headers,
                intfmt		= ',',
                floatfmt	= ',.15g',
                tablefmt	= tablefmt or INVOICE_FORMAT,
            )

            def fmt( val, hdr, coin  ):
                hdr_split	= hdr.split()  # Eg. "Total USDC" --> ["Total","USDC"]
                if can( hdr_split[0] ) in ( 'total', 'taxes', 'amount', 'net' ):
                    # It's a computed Total/Taxes/Amount/Net; use the line's/column's
                    # cryptocurrency to round.  Do not round Price, because multiples of a
                    # fractional price are significant, even if the precision is greater than the
                    # number of decimals supported by the LineItem's Cryptocurrency.
                    decimals	= deci( hdr_split[1] if len( hdr_split ) > 1 else coin )
                    val		= round( val, decimals )
                return val

            # Produce the page line-items.  We must round each line-item's numeric price values
            # according to the target coin.
            table_rows		= [
                [
                    fmt( line[i], h, line[headers_can.index( can( 'Coin' ))] )
                    for i,h in zip( selected, headers_selected )
                ]
                for line in page
            ]
            table_headers	= [ h.strip('_') for h in headers_selected ]

            if final and totalize:
                # Include a separator, followed by each cryptocurrency's totalization.  Map
                # total_rows columns:
                #
                #   Account  -> Description
                #   Total    -> Amount
                #   Coin     -> Coin
                #   Currency -> Currency
                table_rows.append( tabulate.SEPARATING_LINE )
                for acc,tax,tot,coin,curr in total_rows:
                    row		= []
                    for h in headers_selected:
                        if can( h ) == can( 'Description' ):
                            row.append( acc )
                        elif can( h ) == can( 'Amount' ):
                            row.append( tot )
                        elif can( h ) == can( 'Taxes' ):
                            row.append( tax )
                        elif can( h ) == can( 'Coin' ):
                            row.append( coin )
                        elif can( h ) == can( 'Currency' ):
                            row.append( curr )
                        else:
                            row.append( None )
                    table_rows.append( row )

            # Presently, the Description column is the only one likely to have a width issue...
            maxcolwidths		= None
            if description_max is None:
                description_max		= INVOICE_DESCRIPTION_MAX
            if description_max:
                desc_i			= headers_can.index( can( "Description" ))
                maxcolwidths	= [
                    description_max if i == desc_i else None
                    for i in selected
                ]
                log.info( f"Maximum col widths {commas( ( f'{h}: {w}' for h,w in zip( table_headers, maxcolwidths ) ), final='and' )}" )

            table		= tabulate_nopad(
                table_rows,
                headers		= table_headers,
                intfmt		= ',',
                floatfmt	= ',.15g',
                tablefmt	= tablefmt or INVOICE_FORMAT,
                maxcolwidths	= maxcolwidths,
            )

            yield page, table, subtotal, total


def layout_invoice(
    inv_dim: Coordinate,			# Printable invoice dimensions, in inches (net page margins).
    inv_margin: int,				# Additional margin around invoice
    rows: int,					# Compute rows, from the number of columns
):
    """Layout an Invoice, in portrait format.  Assumes that we are laying out an invoice in the
    printable area of a page (ie. net of non-printable page margins, eg. on a 8" x 10.5"/13.5"
    viewport onto a 8.5" x 11"/14" Letter/Legal page.

    Rotates the watermark, etc. so its angle is from the lower-left to the upper-right.

                 b
          +--------------+        +--------------+
          |             .         |I.. (img)  Na.|
          |           D.          |--------------|
          |          .            |# D.. u.u.    |
          |        I.             |...           |
          |       .               |         ---- |
          |     A. c              |    BTC  #.## |
          |    .                  |    ETH  #.## |
        a |  P.                   | (terms)      |
          |β.                     | (tax #, ..)  |
          + 90-β                  +--------------+

       tan(β) = b / a, so
       β = arctan(b / a)

    Sets priority:
      -3     : Hindmost backgrounds
      -2     : Things atop background, but beneath contrast-enhancement
      -1     : Contrast-enhancing partially transparent images
       0     : Text, etc. (the default)

    All sizes in mm.

    """
    prio_backing		= -3
    prio_normal			= -2
    prio_contrast		= -1

    if inv_margin is None:
        inv_margin		= 0		# Default; no additional margin (besides page margins)

    inv				= Box( 'invoice', 0, 0, inv_dim.x, inv_dim.y )
    inv_int			= inv.add_region_relative(
        Region( 'inv-interior', x1=+inv_margin, y1=+inv_margin, x2=-inv_margin, y2=-inv_margin )
    ).add_region_proportional(
        # inv-image	-- A full background image, out to the margins; bottom-most in stack
        Image(
            'inv-image',
            priority	= prio_backing,
        )
    )

    a				= inv_int.h
    b				= inv_int.w
    c				= math.sqrt( a * a + b * b )
    β				= math.atan( b / a )
    rotate			= 90 - math.degrees( β )

    # Header: Vendor name & contact on left, Invoice/Quote/Receipt and logo on right
    #           8"
    #     +-------------------------------------------------------------------------------+
    #     | Dominion R&D Corp                                                      INVOICE|
    #     | (vendor info)                                               //////////////////|
    # 2"  | Bill To:                  Invoice No: CLI-20231201-0001     ///16x9 LOGO//////|
    #     | Client Name             Invoice Date: ...                   //////////////////|
    #     | (client info)                    Due: ...                   //////////////////|
    #     + ...                                                         //////////////////+

    # inv-head: Header Image 2"x8" header of Invoice (if no full-page inv-image).  Since our length
    # may be variable for Letter/Legal, compute the length of the header as a fraction of its width.

    head			= inv_int.w * 1/4  / inv_int.h  # eg.   2" x 8"
    foot		    = 1 - inv_int.w * 1/16 / inv_int.h  # eg. 0.5" x 8"

    inv_head			= inv_int.add_region_proportional(
        Image(
            'inv-head',
            y2		= head,
            priority	= prio_normal,
        ),
    )

    # inv-vendor: Vendor name and Invoice label, top of invoice in large font.  The remaining
    # vertical portion of the header contains the 16/9 format Logo, positioned in the LR corner.
    logo			= 1/6				# 1/3" of 2" header for vendor/label
    logo_v_frac			= 1 - logo
    logo_h_frac			= 1 - inv_head.h * logo_v_frac * 16/9 / inv_head.w
    inv_head.add_region_proportional(
        Image(
            'inv-vendor-bg',
            x2		= logo_h_frac,
            y2		= logo,
            priority	= prio_contrast,
        )
    ).add_region(
        Text(
            'inv-vendor',
            align	= 'L',
        )
    )
    inv_head.add_region_proportional(
        Image(
            'inv-vendor-info-bg',
            y1		= logo,
            x2		= logo_h_frac,
            y2		= 1/2,
            priority	= prio_contrast,
        )
    ).add_region_proportional(
        Text(
            'inv-vendor-info',
            y2		= 1/4,   # 3 lines in remaining upper half (2/6) of header
            multiline	= True,
        )
    )

    # inv-client[-info] In lower 1/2 of LHS of header
    inv_head.add_region_proportional(
        Image(
            'inv-client-bg',
            y1		= 1/2,
            y2		= 1/2 + logo,
            x2		= logo_h_frac,
            priority	= prio_contrast,
        )
    ).add_region(
        Text(
            'inv-client',
            align	= 'L',
            italic	= True,
        )
    )
    inv_head.add_region_proportional(
        Image(
            'inv-client-info-bg',
            y1		= 1/2 + logo,
            x2		= logo_h_frac,
            priority	= prio_contrast,
        )
    ).add_region_proportional(
        Text(
            'inv-client-info',
            y2		= 1/4,   # 4 lines in remaining lower half (2/6) of header
            multiline	= True,
            italic	= True,
        )
    )

    # inv-label, inv-logo: Label "Invoice" and 16/9 logo in LR corner
    inv_head.add_region_proportional(
        Image(
            'inv-label-bg',
            x1		= logo_h_frac,
            y2		= logo,
            priority	= prio_contrast,
        )
    ).add_region(
        Text(
            'inv-label',
            align	= 'R'
        )
    )
    inv_head.add_region_proportional(
        Image(
            'inv-logo',
            x1		= logo_h_frac,
            y1		= logo,
            priority	= prio_normal,
        ),
    )

    # inv-body, ...: Image for Body of Invoice;
    # inv-table: Main Invoice text area
    inv_body			= inv_int.add_region_proportional(
        Image(
            'inv-body',
            y1		= head,
            y2		= foot,
            priority	= prio_normal,
        )
    )

    inv_body.add_region_proportional(
        Image(
            'inv-table-bg',
            priority	= prio_contrast,
        ),
    ).add_region_proportional(
        Text(
            'inv-table',
            y2		= 1/rows,
            font	= 'mono',
            #size_ratio	= 9/16,
            multiline	= True,
            bold	= True,
        )
    )

    # inv-foot: Image for bottom of Invoice (if no inv-image)
    inv_int.add_region_proportional(
        Image(
            'inv-foot',
            y1		= foot,
            priority	= prio_normal,
        ),
    )

    # Finally, in front of all other "contrast" images, put the watermark
    inv_int.add_region_proportional(
        Text(
            'inv-watermark',
            x1		= c/b * 10/100,
            y1		= +0/32,
            x2		= c/b * 90/100,
            y2		= +8/32,
            foreground	= int( COLOR[-2], 16 ),  # med grey
            rotate	= -rotate,
            bold	= True,
            italic	= True,
            align	= 'C',
            priority	= prio_contrast,
            text	= "- Sample -",
        )
    )

    return inv


def datetime_advance( dt, years=None, months=None, days=None, hours=None, minutes=None, seconds=None ):
    """Advance a datetime the specified amount.  Differs from timedelta, in that A) months are supported
    (so we must compute the target month, and clamp the day number appropriately).  Otherwise, uses
    timedelta.

    """
    if years or months:
        yr,mo,dy		= dt.year,dt.month,dt.day
        yr		       += years or 0
        mo		       += months or 0
        if mo > 12:
            yr		       += ( mo - 1 ) // 12
            mo			= ( mo - 1 ) % 12 + 1
            assert 1 <= mo <= 12
        _,dy_max		= monthrange( yr, mo )
        if dy > dy_max:
            dy			= dy_max
        dt			= dt.replace( day=1 ).replace( year=yr ).replace( month=mo ).replace( day=dy )
    if days or hours or minutes or seconds:
        dt		       += timedelta( days=days or 0, hours=hours or 0, minutes=minutes or 0, seconds=seconds or 0 )
    return dt


@dataclass
class Contact:
    name: str					# Company or Individual eg. "Dominion Research and Development Corp."
    contact: str				# client/vendor authority eg. "Perry Kundert <perry@dominionrnd.com>"
    phone: Optional[str]	= None
    address: Optional[str]	= None		# multi-line mailing/delivery address
    billing: Optional[str]	= None		# and billing address, if different

    @property
    def info( self ):
        if self.contact:
            yield self.contact
        if self.phone:
            yield self.phone
        if self.address:
            yield ', '.join( filter( None, self.address.split( '\n' )))
        if self.billing:
            yield "Billing: " + ', '.join( filter( None, self.billing.split( '\n' )))


@dataclass
class InvoiceMetadata:
    """Collected Invoice metadata, required to generate an Invoice.  An identical Invoice can be
    issued with multiple different InvoiceMetadata, eg. to different clients (optionally may be
    absent, indicating a generic invoice to an anonymous client).

    """
    vendor: Contact				# Vendor's identifying info
    client: Optional[Contact] = None  		# Client's identifying info (eg. Name, Attn, Address)
    number: Optional[Union[str,int]] = None     # eg. "CLI-20230930-0001" (default: <client>-<date>-<num>)
    date: Optional[datetime] = None		# default: now
    due: Optional[datetime] = None		# default: 1 month
    terms: Optional[str] = None			# default: Net Duration(due - date)
    directory: Optional[Union[str,Path]] = None  # Location of assets (and invoices) (./)
    label: Optional[str] = None			# eg. Invoice


@dataclass
class InvoiceOutput:
    invoice: Invoice
    metadata: InvoiceMetadata
    pdf: fpdf.FPDF
    path: Optional[Path] = None			# optionally written to path


def produce_invoice(
    invoice: Invoice,				# Invoice LineItems, Cryptocurrency Account data
    metadata: InvoiceMetadata,			# vendor, client, number, etc.
    rows: Optional[int]		= None,
    paper_format: Any		= None, 	# 'Letter', 'Legal', 'A4', (x,y) dimensions in mm.
    orientation: Optional[str]	= None,		# available orientations; default portrait, landscape
    image: Optional[Union[Path,str]] = None,  # A custom 8"/10.5" full background image (Path/name relative to directory/'.'
    logo: Optional[Union[Path,str]] = None,  # A custom 16/9 logo image (Path or name relative to directory/'.'
):
    """Produces a PDF containing the supplied Invoice details, optionally with a PAID watermark.

    """
    if ( label := metadata.label ) is None:
        label			= 'Invoice'
    if isinstance( directory := metadata.directory, (str,type(None))):
        directory		= Path( directory or '.' )
    assert isinstance( directory, (Path,type(None)))
    log.info( f"Dir.:  {directory}" )

    if isinstance( image, (str,type(None))):
        image			= directory / ( image or 'inv-image.png' )
        if not image.exists():
            image		= None
    assert isinstance( image, (Path,type(None)))
    log.info( f"Image: {image}" )

    if isinstance( logo, (str,type(None))):
        logo			= directory / ( logo or 'inv-logo.png' )
        if not logo.exists():
            logo		= None
    assert isinstance( logo, (Path,type(None)))
    log.info( f"Logo:  {logo}" )

    # Any datetime WITHOUT a timezone designation is re-interpreted as the local timezone of the
    # invoice issuer, or UTC.
    if ( date := metadata.date ) is None:
        date			= invoice.created
    if date.tzname() is None:
        try:
            zone		= get_localzone()
        except Exception:
            zone		= timezone.utc
        date			= date.astimezone( zone )

    log.info( f"Date:  {date.strftime( INVOICE_STRFTIME )}" )
    if not isinstance( due := metadata.due, datetime ):
        if not due:
            due			= INVOICE_DUE
        log.info( f"Due w/ {due!r}" )
        if is_mapping( due ):
            due			= datetime_advance( date, **dict( due ))
        elif is_listlike( due ):
            due			= datetime_advance( date, *tuple( due ))
        elif isinstance( due, timedelta ):
            due			= date + due
        else:
            raise ValueError( f"Unsupported Invoice due date: {due!r}" )
    log.info( f"Due:   {due.strftime( INVOICE_STRFTIME )}" )
    if ( terms := metadata.terms ) is None:
        terms			= f"Net {Duration( due - date )!r}"
    log.info( f"Terms: {terms}" )

    if ( number := metadata.number ) is None:
        cli			= metadata.client.name.split()[0].upper()[:3] if metadata.client else 'INV'
        ymd			= date.strftime( '%Y%m%d' )
        key			= f"{cli}-{ymd}"
        produce_invoice.inv_count[key] += 1
        num			= produce_invoice.inv_count[key]
        number			= f"{cli}-{ymd}-{num:04d}"
    log.info( f"Num.:  {number}" )

    # We can now capture the actual metadata used for this specific invoice
    metadata			= InvoiceMetadata(
        vendor		= metadata.vendor,
        client		= metadata.client,
        number		= number,
        date		= date,
        due		= due,
        terms		= terms,
        directory	= directory,
        label		= label,
    )

    # Default to full page, given the desired paper and orientation.  All PDF dimensions are mm.
    invs_pp,orientation,page_xy,pdf,comp_dim = layout_pdf(
        paper_format	= paper_format,
        orientation	= orientation,
    )
    log.info( f'Dim.: {comp_dim.x / MM_IN:6.3f}" x {comp_dim.y / MM_IN:6.3f}"' )

    # TODO: compute rows based on line lengths; the longer the line, the smaller the lines
    # required In the mean time, assume we can only fit about 1/2 the number of line-item rows,
    # as the invoice has total lines, due to the details, totals and currency conversion ratios.
    if rows is None:
        rows			= INVOICE_ROWS

    # Compute the Invoice layout on the page.  All page layouts are specified in inches.
    inv_dim			= Coordinate( comp_dim.x / MM_IN, comp_dim.y / MM_IN )

    inv				= layout_invoice( inv_dim=inv_dim, inv_margin=0, rows=rows )
    inv_elements		= list( inv.elements() )
    inv_tpl			= fpdf.FlexTemplate( pdf, inv_elements )

    p_cur			= None
    details			= list( invoice.tables() )
    for i,(page,tbl,sub,tot) in enumerate( details ):
        p,(offsetx,offsety)		= page_xy( i )
        if p != p_cur:
            pdf.add_page()

        here			= Path( __file__ ).resolve().parent
        layout			= here.parent / 'layout'
        #crypto			= here / 'Crypto'

        final			= i + 1 == len( details )
        inv_tpl['inv-image']	= image
        inv_tpl['inv-logo']	= logo
        inv_tpl['inv-label']	= f"{metadata.label} (page {p+1}/{len( details )})"
        inv_tpl['inv-label-bg']	= layout / '1x1-ffffffbf.png'

        inv_tpl['inv-vendor']	= metadata.vendor.name
        inv_tpl['inv-vendor-bg'] = layout / '1x1-ffffffbf.png'
        inv_tpl['inv-vendor-info'] = '\n'.join( metadata.vendor.info )
        inv_tpl['inv-vendor-info-bg'] = layout / '1x1-ffffffbf.png'

        if metadata.client:
            inv_tpl['inv-client'] = "Bill To: " + metadata.client.name
            inv_tpl['inv-client-bg'] = layout / '1x1-ffffffbf.png'
            inv_tpl['inv-client-info'] = '\n'.join( metadata.client.info )
            inv_tpl['inv-client-info-bg'] = layout / '1x1-ffffffbf.png'

        dets			= tabulate_nopad(
            [
                [ f'{metadata.label} #:', metadata.number ],
                [ 'Date:', metadata.date.strftime( INVOICE_STRFTIME ) ],
                [ 'Due:', metadata.due.strftime( INVOICE_STRFTIME ) ],
                [ 'Terms:', metadata.terms ]
            ],
            colalign=( 'right', 'left' ), tablefmt='plain'
        )

        exch			= conversions_table( invoice.conversions )
        exch_date		= invoice.resolved.strftime( INVOICE_STRFTIME )
        inv_table		= (dets, tbl,)
        if final:
            inv_table	       += ( f"CONVERSION RATIOS (est. {exch_date}):\n{exch}", )
        inv_tpl['inv-table']	= '\n\n'.join( inv_table )
        inv_tpl['inv-table-bg']	= layout / '1x1-ffffffbf.png'

        inv_tpl.render( offsetx=offsetx, offsety=offsety )
    # Caller already has the Invoice; return the PDF and computed InvoiceMetadata
    return (paper_format,orientation),pdf,metadata
produce_invoice.inv_count	= defaultdict( int )  # noqa: E305


def write_invoices(
    invoices: Sequence[Tuple[Invoice,InvoiceMetadata]],  # sequence of [ (Invoice, InvoiceMetadata), ... ] or { "<name>": Invoice, ... }
    filename		= True,		# A file name/Path, if PDF output to file is desired; ''/True implies default., False no file
    **kwds
) -> Union[InvoiceOutput, Exception]:
    """Generate unique cryptocurrency account(s) for each client invoice, generate the invoice,
    and (optionally) write them to files.  Yields a sequence of the generated invoice PDF names
    and details.

    If an Exception is raised during Invoice generation, a (None, <Exception>) is generated,
    instead of a ("name", <InvoiceOutput).

    """
    if filename is None:
        filename		= True
    for invoice,metadata in invoices:  # Provides the supplied invoice,metadata...
        try:
            # and receives the transformed (specialized) metadata.
            _,pdf,metadata		= produce_invoice(
                invoice	= invoice,
                metadata = metadata,
                **kwds
            )

            accounts		= invoice.accounts
            assert accounts, \
                "At least one Cryptocurrency account must be specified"

            name		= (( '' if filename is True else filename ) or FILENAME_FORMAT ).format(
                name	= metadata.number,
                date	= datetime.strftime( metadata.date, '%Y-%m-%d' ),
                time	= datetime.strftime( metadata.date, '%H.%M.%S'),
                crypto	= accounts[0].crypto,
                address	= accounts[0].address,
            )
            if not name.lower().endswith( '.pdf' ):
                name		       += '.pdf'

            path			= None
            if filename is not False:
                path		= metadata.directory.resolve() / name
                log.warning( f"Writing Invoice {metadata.number!r} to: {path}" )
                pdf.output( path )

            output		= InvoiceOutput(
                invoice	= invoice,
                metadata = metadata,
                pdf	= pdf,
                path	= path,
            )
        except (BaseException, ConversionError) as exc:
            name, output	= None, exc

        yield name, output
