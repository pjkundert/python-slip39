
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

from dataclasses	import dataclass
from collections	import namedtuple
from typing		import Dict, Union, Any

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
    'price',				# 1.98 eg. $USDC, Fraction( 10000, 12 ) * 10**9, eg. ETH Gwei per dozen, in Wei
    'tax',				# 0.05, Fraction( 5, 100 ) eg. GST, added to amount, 1.05 GST, included in amount
    'decimals',				# Number of decimals to display computed amounts, eg. 2.
    'currency'				# USDC
] )


@dataclass
class Item:
    description: str				# "Widgets for The Thing"
    price: Any					# 1.98 eg. $USDC, Fraction( 10000, 12 ) * 10**9, eg. ETH Gwei per dozen, in Wei
    units: Union[int,float]	= 1		# 198, 1.5
    tax: Any			= None		# 0.05, Fraction( 5, 100 ) eg. GST, added to amount, 1.05 GST, included in amount
    decimals: int		= 2   	 	# Number of decimals to display computed amounts, eg. 2.
    currency: str		= "USDC"


class Line( Item ):
    def amounts( self ):
        """Computes the total amount, and taxes for the Line"""
        amount			= self.units * self.price
        taxes			= 0
        taxinf			= 'no tax'
        if self.tax:
            if self.tax < 1:
                taxinf		= f"{float( self.tax * 100 ):.2f}% added"
                taxes		= amount * self.tax
            elif self.tax > 1:
                taxinf		= f"{float(( self.tax - 1 ) * 100 ):.2f}% incl."
                taxes		= amount - amount / self.tax
                amount	       -= taxes

        return amount, taxes, taxinf  # denominated in self.currency


class Total:
    """The totals for some invoice line items.

    Can emit the line items in groups with summary sub-totals and a final total.

    Reframes the price of each line in terms of the Total's currency (default: USDC).


    """
    def __init__(
        self, lines,
        currency		= None,
        w3_url			= None,
        use_provider		= None,
    ):
        self.lines		= list( lines )
        self.currency		= currency or "USDC"
        self.w3_url		= w3_url
        self.use_provider	= use_provider

    def headers( self ):
        """Output the headers to use in tabular formatting of iterator"""
        return [
            'Line',
            'Description',
            'Units',
            'Price',
            'Tax',
            'Tax %',
            'Amount',
            'Taxes',
            f"Total {self.currency}"
        ]

    def iter( self ):
        """Iterate of lines, computing totals"""
        # Get all the eg. BTC / USDC ratios for the Line-item currency, vs. the Total currency
        self_curr_info		= tokeninfo( self.currency, w3_url=self.w3_url, use_provider=self.use_provider )
        self_curr_addr		= self_curr_info['address']
        currencies		= {}
        for line in self.lines:
            line_curr_info	= tokeninfo( line.currency, w3_url=self.w3_url, use_provider=self.use_provider )
            line_curr_addr	= line_curr_info['address']
            if line_curr_addr not in currencies:
                currencies[line_curr_addr] = tokenratio( line_curr_addr, self_curr_addr )[2]

        total			= 0.
        for i,line in enumerate( self.lines ):
            amount,taxes,taxinf	= line.amounts()
            amount_curr		= amount
            line_curr_info	= tokeninfo( line.currency, w3_url=self.w3_url, use_provider=self.use_provider )
            line_curr_addr	= line_curr_info['address']
            if line_curr_addr != self_curr_addr:
                amount_curr    *= currencies[line_curr_addr]
            total	       += float( amount_curr )
            yield i, line.description, line.units, line.price, line.currency, taxinf, amount, taxes, total

    def pages( self, page = None, rows = 10 ):
        """Yields a sequence of lists containing rows, paginated into 'rows' chunks."""
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


#
# Prices
#
# Beware:
#     https://samczsun.com/so-you-want-to-use-a-price-oracle/
#
# We use a time-weighted average oracle provided by 1inch to avoid some of these issues:
#     https://docs.1inch.io/docs/spot-price-aggregator/introduction
#
class Prices:
    """Retrieve current Crypto prices, using a time-weighted oracle API.

    """
    pass


def produce_pdf(
    client: Dict[str,str],      	# Client's identifying info (eg. Name, Attn, Address)
    vendor: Dict[str,str],		# Vendor's identifying info
    number: str,			# eg. "INV-20230930"
    terms: str,    			# eg. "Payable on receipt in $USDC, $ETH, $BTC"
):
    """Produces a PDF containing the supplied Invoice details, optionally with a PAID watermark.



    """
    pass
