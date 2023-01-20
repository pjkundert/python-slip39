
from fractions		import Fraction
import json

import pytest

from .artifact		import LineItem, Invoice

line_amounts			= [
    [
        LineItem(
            description	= "Widgets for the Thing",
            units	= 198,
            price	= 2.01,
            tax		= Fraction( 5, 100 ),  # exclusive
            currency	= 'US Dollar',
        ),
        ( 417.879, 19.899, "5% added" ),
    ], [
        LineItem(
            description	= "More Widgets",
            units	= 2500,
            price	= Fraction( 201, 1000 ),
            tax		= Fraction( 5, 100 ),  # exclusive
            currency	= 'ETH',
        ),
        ( 527.625, 25.125, "5% added" ),
    ], [
        LineItem(
            description	= "Something else, very detailed and elaborate to explain",
            units	= 100,
            price	= Fraction( 201, 10000 ),
            tax		= Fraction( 105, 100 ),  # inclusive
            decimals	= 8,
            currency	= 'Bitcoin',
        ),
        ( 2.01, 0.09571, "5% incl." ),
    ], [
        LineItem(
            description	= "Buy some Holo hosting",
            units	= 12,
            price	= 10000,
            tax		= Fraction( 5, 100 ),  # inclusive
            currency	= 'HoloToken',
        ),
        ( 126000, 6000, "5% added" ),
    ], [
        LineItem( "Worthless", 12345.6789, currency='ZEENUS' ),
        ( 12345.6789, 0, "no tax"),
    ], [
        LineItem( "Simple", 12345.6789 ),  # currency default None ==> USD
        ( 12345.6789, 0, "no tax" ),
    ],
]


@pytest.mark.parametrize( "line, amounts", line_amounts )
def test_LineItem( line, amounts ):
    amount,taxes,taxinf	= amounts
    assert line.net() == (
        pytest.approx( amount, abs=10 ** -3 ),
        pytest.approx( taxes,  abs=10 ** -3 ),
        taxinf
    )


def test_tabulate():
    total			= Invoice( [
        line
        for line,_ in line_amounts
    ], currencies=["HOT", "ETH", "BTC", "USD"] )

    print( json.dumps( list( total.pages() ), indent=4, default=str ))

    tables			= list( total.tables() )
    for t in tables:
        print( t )

    # Can't test until we can fake up fixed token values

    tables			= list( total.tables(
        columns=('Description', 'Units', 'Currency', 'Symbol', 'Price', 'Tax %', 'Taxes', 'Amount', 'Total USDC'),
    ))
    for t in tables:
        print( t )

    # Get the default formatting for line's w/ currencies w/ 0 decimals, 0 value
    worthless = '\n\n'.join( Invoice( [
        line
        for line,_ in line_amounts
        if line.currency in ("ZEENUS", )
    ], currencies=["HOT", "ETH", "BTC", "USD"] ).tables() )
    print( worthless )
    assert worthless == """\
|   Line | Description   |   Units |   Price |   Amount | Tax %   |   Taxes | Currency   | Symbol   |   Total HOT |   Total USDC |   Total WBTC |   Total WETH |   Taxes HOT |   Taxes USDC |   Taxes WBTC |   Taxes WETH |
|--------+---------------+---------+---------+----------+---------+---------+------------+----------+-------------+--------------+--------------+--------------+-------------+--------------+--------------+--------------|
|      0 | Worthless     |       1 |  12,346 |   12,346 | no tax  |       0 | ZEENUS     | ZEENUS   |           0 |            0 |            0 |            0 |           0 |            0 |            0 |            0 |"""

    # No conversions of non-0 values; default Invoice currency is USD.  Longest digits should be 2
    shorter = '\n\n'.join( Invoice( [
        line
        for line,_ in line_amounts
        if line.currency in ("ZEENUS", None) or line.currency.upper().startswith( 'US' )
    ] ).tables() )
    print( shorter )
    assert shorter == """\
|   Line | Description           |   Units |     Price |    Amount | Tax %    |   Taxes | Currency   | Symbol   |   Total USDC |   Taxes USDC |
|--------+-----------------------+---------+-----------+-----------+----------+---------+------------+----------+--------------+--------------|
|      0 | Widgets for the Thing |     198 |      2.01 |    417.88 | 5% added |   19.90 | US Dollar  | USDC     |       417.88 |        19.90 |
|      1 | Worthless             |       1 | 12,345.68 | 12,345.68 | no tax   |    0.00 | ZEENUS     | ZEENUS   |       417.88 |        19.90 |
|      2 | Simple                |       1 | 12,345.68 | 12,345.68 | no tax   |    0.00 | USD        | USDC     |    12,763.56 |        19.90 |"""
