
from fractions		import Fraction

import pytest

from .artifact		import Line, Total

line_amounts			= [
    [
        Line(
            description	= "Widgets for the Thing",
            units	= 198,
            price	= 2.01,
            tax		= Fraction( 5, 100 ),  # exclusive
            decimals	= 2,
            currency	= 'USDC',
        ),
        ( 397.98, 19.90, "5.00% added" ),
    ], [
        Line(
            description	= "More Widgets",
            units	= 198,
            price	= Fraction( 201, 1000 ),
            tax		= Fraction( 5, 100 ),  # exclusive
            decimals	= 2,
            currency	= 'wETH',
        ),
        ( 397.98, 19.90, "5.00% added" ),
    ], [
        Line(
            description	= "Something else",
            units	= 198,
            price	= Fraction( 201, 10000 ),
            tax		= Fraction( 105, 100 ),  # inclusive
            decimals	= 2,
            currency	= 'wBTC',
        ),
        ( 379.03, 18.95, "5.00% incl." ),
    ], [
        Line( "Simple", 1.98 ),
        ( 1.98, 0, "no tax" ),
    ],
]


@pytest.mark.parametrize( "line, amounts", line_amounts )
def test_Line( line, amounts ):
    amount,taxes,taxinf	= amounts
    assert line.amounts() == (
        pytest.approx( amount, abs=10 ** -line.decimals ),
        pytest.approx( taxes,  abs=10 ** -line.decimals ),
        taxinf
    )


WETH				= "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"


def test_Total():
    total			= Total( [
        line
        for line,_ in line_amounts
    ], currencies=["HOT",WETH,"USDC"] )

    tables			= list( total.tables() )
    for t in tables:
        print( t )

    # Can't test until we can fake up fixed token values
#     assert tables == [
#         """\
# |   Line | Description           |   Units |   Currency | Price   |   Amount | Tax #       |     Tax % |     Taxes |        Total HOT |   Total USDC |   Total WETH |       Taxes HOT |   Taxes USDC |   Taxes WETH |
# |--------+-----------------------+---------+------------+---------+----------+-------------+-----------+-----------+------------------+--------------+--------------+-----------------+--------------+--------------|
# |      0 | Widgets for the Thing |     198 |     2.01   | USDC    |     0.05 | 5.00% added | 397.98    | 19.899    | 208587           |       397.98 |     0.260934 | 10429.3         |       19.899 |    0.0130467 |
# |      1 | More Widgets          |     198 |     0.201  | WETH    |     0.05 | 5.00% added |  39.798   |  1.9899   |      3.20225e+07 |     61098.4  |    40.0589   |     1.60113e+06 |     3054.92  |    2.00295   |
# |      2 | Something else        |     198 |     0.0201 | WBTC    |     1.05 | 5.00% incl. |   3.79029 |  0.189514 |      7.31847e+07 |    139635    |    91.5513   |     3.65924e+06 |     6981.76  |    4.57757   |
# |      3 | Simple                |       1 |     1.98   | USDC    |          | no tax      |   1.98    |  0        |      7.31858e+07 |    139637    |    91.5526   |     3.65924e+06 |     6981.76  |    4.57757   |
# """,
#     ]

