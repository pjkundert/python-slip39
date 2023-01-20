
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
from collections	import namedtuple
from typing		import Dict, Union, Optional
from fractions		import Fraction

from tabulate		import tabulate

from ..util		import uniq, commas, is_listlike
from ..defaults		import INVOICE_CURRENCY
from ..layout		import Region, Text, Image, Box, Coordinate
from .ethereum		import tokeninfo, tokenratio

"""
Invoice artifacts:

    Invoice/Quote	-- States deliverables, prices/taxes, and totals in various currencies

    Receipt		-- The Invoice, marked "PAID"


"""
log				= logging.getLogger( "customer" )


# An invoice line-Item contains the details of a component of a transaction.  It is priced in a
# currency, with a number of 'units', and a 'price' per unit.
#
# The 'tax' is a proportion of the computed total amount allocated to taxation; if <1 (eg. 0.05 or
# 5%), then it is added to the total amount; if > 1 (eg. 1.05 or 5%), then the prices is assumed to
# be tax-inclusive and it is subtracted from the computed amount.
#
# Each line-Item may be expressed in a different currency.
Item				= namedtuple( 'Item', [
    'description',			# "Widgets for The Thing"
    'units',				# 198
    'price',				# 1.98 eg. $USD, Fraction( 10000, 12 ) * 10**9, eg. ETH Gwei per dozen, in Wei
    'tax',				# 0.05, Fraction( 5, 100 ) eg. GST, added to amount, 1.05 GST, included in amount
    'decimals',				# Number of decimals to display computed amounts, eg. 2.  Default: currency's decimals//3
    'currency'				# USD
] )


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
        """Computes the LineItem total 'amount', the 'taxes', and info on tax charged.

        Uses the default Invoice Currency if none specified.

        """
        amount			= self.units * self.price
        taxes			= 0
        taxinf			= 'no tax'
        if self.tax:
            if self.tax < 1:
                taxinf		= f"{round( float( self.tax * 100 ), 2):g}% added"
                taxes		= amount * self.tax
                amount	       += taxes
            elif self.tax > 1:
                taxinf		= f"{round( float(( self.tax - 1 ) * 100 ), 2):g}% incl."
                taxes		= amount - amount / self.tax
        return amount, taxes, taxinf  # denominated in self.currencies


class Invoice:
    """The totals for some invoice line items, in terms of some cryptocurrencies.  Currencies may be
    supplied by ERC-20 token contract address or by symbol or full name (for known cryptocurrencies
    eg. "BTC", "ETH", or some known ERC-20 tokens (~top 100).  Presently, we only support invoice cryptocurrencies that
    have a highly-liquid Ethereum ERC-20 "proxy", eg. ETH/wETH, BTC/wBTC

    Can emit the line items in groups with summary sub-totals and a final total.

    Reframes the price of each line in terms of the Invoice's currencies (default: USDC), providing
    "Total <SYMBOL>" and "Taxes <SYMBOL>" for each Cryptocurrency symbols.

    Now that we have Web3 details, we can query tokeninfos and hence format currency decimals
    correctly.

    """
    def __init__(
        self, lines,
        currencies		= None,
        w3_url			= None,
        use_provider		= None,
    ):
        self.lines		= list( lines )
        self.w3_url		= w3_url
        self.use_provider	= use_provider
        if currencies:
            currencies		= [ currencies ] if isinstance( currencies, str ) else list( currencies )
        if not currencies:
            currencies    	= [ INVOICE_CURRENCY ]
        # Get all Invoice currencies' tokeninfo unique/sorted by token symbol.  This is where we
        # must convert any proxied fiat/crypto-currencies (USD, BTC) into available ERC-20 tokens.
        self.currencies		= sorted(
            uniq(
                (
                    tokeninfo( currency, w3_url=self.w3_url, use_provider=self.use_provider )
                    for currency in currencies
                ), key=lambda c: c['symbol'],
            ), key=lambda c: c['symbol']
        )

    def headers( self ):
        """Output the headers to use in tabular formatting of iterator.  By default, we'd recommend hiding any starting
        with an _ prefix."""
        return (
            'Line',
            'Description',
            'Units',
            'Price',
            'Amount',
            '_Tax',
            'Tax %',
            'Taxes',
            'Currency',
            'Symbol',
            '_Decimals',
            '_Token',
        ) + tuple(
            f"Total {currency['symbol']}"
            for currency in self.currencies
        ) + tuple(
            f"Taxes {currency['symbol']}"
            for currency in self.currencies
        )

    def __iter__( self ):
        """Iterate of lines, computing totals in each Invoice.currencies

        Note that numeric values may be int, float or Fraction, and these are retained through
        normal mathematical operations.

        """

        # Get all the eg. wBTC / USDC value ratios for the Line-item currency, vs. each Invoice
        # currency at once, in case the iterator takes considerable time; we don't want to risk that
        # memoization "refresh" the token values while generating the invoice!

        currencies		= {}
        for line in self.lines:
            line_currency	= line.currency or INVOICE_CURRENCY
            line_curr		= tokeninfo( line_currency, w3_url=self.w3_url, use_provider=self.use_provider )
            for self_curr in self.currencies:
                if (line_curr['address'],self_curr['address']) not in currencies:
                    currencies[line_curr['address'],self_curr['address']] = tokenratio( line_curr['address'], self_curr['address'] )[2]

        tot			= {
            self_curr['symbol']: 0.
            for self_curr in self.currencies
        }
        tax			= {
            self_curr['symbol']: 0.
            for self_curr in self.currencies
        }

        for i,line in enumerate( self.lines ):
            line_currency	= line.currency or INVOICE_CURRENCY
            line_amount,line_taxes,line_taxinf = line.net()
            line_curr		= tokeninfo( line_currency, w3_url=self.w3_url, use_provider=self.use_provider )
            line_symbol		= line_curr['symbol']
            line_decimals	= line_curr['decimals'] // 3 if line.decimals is None else line.decimals
            for self_curr in self.currencies:
                if line_curr == self_curr:
                    tot[self_curr['symbol']] += line_amount
                    tax[self_curr['symbol']] += line_taxes
                else:
                    tot[self_curr['symbol']] += line_amount * currencies[line_curr['address'],self_curr['address']]
                    tax[self_curr['symbol']] += line_taxes  * currencies[line_curr['address'],self_curr['address']]
            yield (
                i,			# The LineItem #, and...
                line.description,
                line.units,
                line.price,
                line_amount,
                line.tax,
                line_taxinf,
                line_taxes,
                line_currency,		# the line's currency
                line_symbol,		# and Token symbol
                line_decimals,		# the desired number of decimals
                line_curr,		# and the associated tokeninfo
            ) + tuple(
                tot[self_curr['symbol']]
                for self_curr in self.currencies
            ) + tuple(
                tax[self_curr['symbol']]
                for self_curr in self.currencies
            )

    def pages(
        self,
        page		= None,
        rows		= 10,
    ):
        """Yields a sequence of lists containing rows, paginated into 'rows' chunks.

        """
        page_i,page_l		= 0, []
        for row in iter( self ):
            page_l.append( row )
            if len( page_l ) >= rows:
                if page is None or page == page_i:
                    yield page_l
                page_i,page_l	= page_i+1,[]
        if page_l:
            if page is None or page == page_i:
                yield page_l

    def tables(
        self, *args,
        tablefmt	= None,
        columns		= None,		# list (ordered) set/predicate (unordered)
        **kwds				# page, rows, ...
    ):
        """Tabulate columns in a textual table.

        The 'columns' is a filter (a set/list/tuple or a predicate) that selects the columns desired.

        """
        headers			= self.headers()
        if columns:
            if is_listlike( columns ):
                selected	= tuple( self.headers().index( h ) for h in columns )
                assert not any( i < 0 for i in selected ), \
                    f"Columns not found: {commas( h for h in headers if h not in columns )}"
            elif hasattr( columns, '__contains__' ):
                selected	= tuple( i for i,h in enumerate( headers ) if h in columns )
                assert selected, \
                    "No columns matched"
            else:
                selected	= tuple( i for i,h in enumerate( headers ) if columns( h ) )
        else:
            # Default; just ignore _... columns
            selected		= tuple( i for i,h in enumerate( headers ) if not h.startswith( '_' ) )
        headers_selected	= tuple( headers[i] for i in selected )
        log.info( f"Tabulating indices {commas(selected, final='and')}: {commas( headers_selected, final='and' )}" )
        pages			= list( self.pages( *args, **kwds ))
        decimals_i		= headers.index( '_Decimals' )
        decimals		= max( line[decimals_i] for page in pages for line in page )
        assert decimals < 32, \
            f"Invalid decimals: {decimals}"
        floatfmt		= f",.{decimals}f"
        intfmt			= ","
        for page in pages:
            yield tabulate(
                [[line[i] for i in selected] for line in page],
                headers		= headers_selected,
                intfmt		= intfmt,
                floatfmt	= floatfmt,
                tablefmt	= tablefmt or 'orgtbl',
            )


def layout_invoice(
    inv_size: Coordinate,
    inv_margin: int,
    num_lines: int		= 10,
):
    """Layout an Invoice, in portrait format.

     Rotate the  watermark, etc. so its angle is from the lower-left to the upper-right.

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
    """
    prio_backing		= -3
    prio_normal			= -2  # noqa: F841
    prio_contrast		= -1

    inv				= Box( 'invoice', 0, 0, inv_size.x, inv_size.y )
    inv_interior		= inv.add_region_relative(
        Region( 'inv-interior', x1=+inv_margin, y1=+inv_margin, x2=-inv_margin, y2=-inv_margin )
    )

    a				= inv_interior.h
    b				= inv_interior.w
    c				= math.sqrt( a * a + b * b )
    β				= math.atan( b / a )      # noqa: F841
    rotate			= 90 - math.degrees( β )  # noqa: F841

    inv_top			= inv_interior.add_region_proportional(
        Region( 'inv-top', x1=0, y1=0, x2=1, y2=1/6 )
    ).add_region_proportional(
        Image(
            'inv-top-bg',
            priority	= prio_backing,
        ),
    )

    inv_top.add_region_proportional(
        Image(
            'inv-label-bg',
            x1		= 0,
            y1		= 5/8,
            x2		= 1/4,
            y2		= 7/8,
            priority	= prio_contrast,
        )
    ).add_region(
        Text(
            'inv-label',
            font	= 'mono',
            text	= "Invoice",
        )
    )
    inv_body			= inv_interior.add_region_proportional(
        Region( 'inv-body', x1=0, y1=1/6, x2=1, y2=1 )
    )

    rows			= 15
    for r in range( rows ):
        inv_body.add_region_proportional(
            Text(
                f"line-{c}",
                x1	= 0,
                y1	= r/rows,
                x2	= 1,
                y2	= (r+1)/rows,
                font	= 'mono',
                bold	= True,
                size_ratio = 9/16,
            )
        )


def produce_invoice(
    client: Dict[str,str],      	# Client's identifying info (eg. Name, Attn, Address)
    vendor: Dict[str,str],		# Vendor's identifying info
    invoice_number: str,		# eg. "INV-20230930"
    terms: str,    			# eg. "Payable on receipt in $USDC, $ETH, $BTC"
):
    """Produces a PDF containing the supplied Invoice details, optionally with a PAID watermark.



    """
    pass
