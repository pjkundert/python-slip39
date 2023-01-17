
from fractions		import Fraction

import pytest

from .artifact		import Line


@pytest.mark.parametrize( "line, amounts", [
    [
        Line(
            description	= "Widgets for the Thing",
            units	= 198,
            price	= 2.01,
            tax		= Fraction( 5, 100 ),
            decimals	= 2,
            currency	= 'USDC',
        ),
        ( 397.98, 19.90, "5.00% added" ),
    ], [
        Line(
            description	= "Widgets for the Thing",
            units	= 198,
            price	= Fraction( 201, 100 ),
            tax		= Fraction( 5, 100 ),
            decimals	= 2,
            currency	= 'USDC',
        ),
        ( 397.98, 19.90, "5.00% added" ),
    ], [
        Line(
            description	= "Widgets for the Thing",
            units	= 198,
            price	= Fraction( 201, 100 ),
            tax		= Fraction( 105, 100 ),
            decimals	= 2,
            currency	= 'USDC',
        ),
        ( 379.03, 18.95, "5.00% incl." ),
    ], [
        Line( "Simple", 1.98 ),
        ( 1.98, 0, "no tax" ),
    ],
])
def test_Line( line, amounts ):
    amount,taxes,taxinf	= amounts
    assert line.amounts() == (
        pytest.approx( amount, abs=10 ** -line.decimals ),
        pytest.approx( taxes,  abs=10 ** -line.decimals ),
        taxinf
    )
