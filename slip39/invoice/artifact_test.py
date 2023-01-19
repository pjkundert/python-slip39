
from fractions		import Fraction
import json

import pytest

from .artifact		import LineItem, Total

line_amounts			= [
    [
        LineItem(
            description	= "Widgets for the Thing",
            units	= 198,
            price	= 2.01,
            tax		= Fraction( 5, 100 ),  # exclusive
            decimals	= 2,
            currency	= 'USDC',
        ),
        ( 417.879, 19.899, "5% added" ),
    ], [
        LineItem(
            description	= "More Widgets",
            units	= 2500,
            price	= Fraction( 201, 1000 ),
            tax		= Fraction( 5, 100 ),  # exclusive
            decimals	= 2,
            currency	= 'wETH',
        ),
        ( 527.625, 25.125, "5% added" ),
    ], [
        LineItem(
            description	= "Something else, very detailed and elaborate to explain",
            units	= 100,
            price	= Fraction( 201, 10000 ),
            tax		= Fraction( 105, 100 ),  # inclusive
            decimals	= 2,
            currency	= 'wBTC',
        ),
        ( 2.01, 0.09571, "5% incl." ),
    ], [
        LineItem( "Simple", 12345.6789 ),
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


WETH				= "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


def test_Total():
    total			= Total( [
        line
        for line,_ in line_amounts
    ], currencies=["HOT",WETH,"USDC"] )

    print( json.dumps( list( total.pages() ), indent=4, default=str ))

    tables			= list( total.tables() )
    for t in tables:
        print( t )

    # Can't test until we can fake up fixed token values

    tables			= list( total.tables(
        columns=('Description', 'Units', 'Price', 'Tax %', 'Taxes', 'Amount'),
    ))
    for t in tables:
        print( t )
