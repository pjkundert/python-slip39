import json

from fractions		import Fraction

import pytest

import tabulate

from ..api		import account
from .artifact		import LineItem, Invoice, conversions_remaining, conversions_table

SEED_ZOOS			= 'zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong'


def test_conversions():
    print( f"tabulate version: {tabulate.__version__}" )
    c0_tbl = tabulate.tabulate( [[ 1.23],[12345.6789],[.0001234]], floatfmt=",.6g", tablefmt="orgtbl" )
    print( f"\n{c0_tbl}" )
    assert c0_tbl == """\
|      1.23      |
| 12,345.7       |
|      0.0001234 |"""

    c1				= {
        ('ETH','USD'):	1234.56,
        ('BTC','USD'):	23456.78,
        ('BTC','ETH'): None,
    }
    c1_tbl			= conversions_table( c1 )
    print( '\n' + c1_tbl )
    assert c1_tbl == """\
| Symbol   |   BTC |   ETH |       USD |
|----------+-------+-------+-----------|
| BTC      |     1 |     ? | 23,456.8  |
| ETH      |       |     1 |  1,234.56 |
| USD      |       |       |      1    |"""

    c_simple			= dict( c1 )
    c_simple_i			= 0
    while ( conversions_remaining( c_simple )):
        c_simple_i	       += 1
    assert c_simple_i == 2
    c_simple_tbl		= conversions_table( c_simple )
    print( c_simple_tbl )
    assert c_simple_tbl == """\
| Symbol   |         BTC |          ETH |       USD |
|----------+-------------+--------------+-----------|
| BTC      | 1           | 19.0001      | 23,456.8  |
| ETH      | 0.0526313   |  1           |  1,234.56 |
| USD      | 4.26316e-05 |  0.000810005 |      1    |"""

    c_w_doge			= dict( c1, ) | { ('DOGE','BTC'): .00000385, ('DOGE','USD'): None }
    c_w_doge_i			= 0
    while ( conversions_remaining( c_w_doge )):
        c_w_doge_i	       += 1
    assert c_w_doge_i == 2
    assert c_w_doge == {
        ('BTC', 'ETH'): pytest.approx( 19.00011, rel=1/1000 ),
        ('BTC', 'USD'): pytest.approx( 23456.78, rel=1/1000 ),
        ('ETH', 'BTC'): pytest.approx( 0.052631, rel=1/1000 ),
        ('ETH', 'USD'): pytest.approx( 1234.56,  rel=1/1000 ),
        ('USD', 'BTC'): pytest.approx( 4.263159e-05, rel=1/1000 ),
        ('USD', 'ETH'): pytest.approx( 8.100051e-04, rel=1/1000 ),
        ('BTC', 'DOGE'): pytest.approx( 259740.2597, rel=1/1000 ),
        ('DOGE', 'BTC'): pytest.approx( 3.85e-06, rel=1/1000 ),
        ('DOGE', 'ETH'): pytest.approx( 7.31504e-05, rel=1/1000 ),
        ('DOGE', 'USD'): pytest.approx( 0.090308, rel=1/1000 ),
        ('ETH', 'DOGE'): pytest.approx( 13670.45839, rel=1/1000 ),
        ('USD', 'DOGE'): pytest.approx( 11.07314216, rel=1/1000 ),
    }
    c_w_doge_tbl		= conversions_table( c_w_doge )
    print( c_w_doge_tbl )
    assert c_w_doge_tbl == """\
| Symbol   |         BTC |         DOGE |          ETH |            USD |
|----------+-------------+--------------+--------------+----------------|
| BTC      | 1           | 259,740      | 19.0001      | 23,456.8       |
| DOGE     | 3.85e-06    |       1      |  7.31504e-05 |      0.0903086 |
| ETH      | 0.0526313   |  13,670.5    |  1           |  1,234.56      |
| USD      | 4.26316e-05 |      11.0731 |  0.000810005 |      1         |"""

    c_bad			= dict( c1, ) | { ('DOGE','USD'): None }
    with pytest.raises( Exception ) as c_bad_exc:
        c_bad_i			= 0
        while ( done := conversions_remaining( c_bad, verify=True )):
            c_bad_i	       += 1
        assert done is None
    assert 'Failed to find ratio(s) for DOGE/USD via BTC/ETH, BTC/USD and ETH/USD' in str( c_bad_exc )
    assert c_bad_i == 2

    assert conversions_remaining( c_bad ) == "Failed to find ratio(s) for DOGE/USD via BTC/ETH, BTC/USD and ETH/USD"


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
    accounts			= [
        account( SEED_ZOOS, crypto='Ripple' ),
        account( SEED_ZOOS, crypto='Ethereum' ),
        account( SEED_ZOOS, crypto='Bitcoin' ),
    ]
    conversions			= {
        ("XRP","BTC"): 60000,
    }

    total			= Invoice(
        [
            line
            for line,_ in line_amounts
        ],
        accounts	= accounts,
        currencies	= [ "USD", "HOT" ],
        conversions	= dict( conversions ),
    )

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

    # Get the default formatting for line's w/ currencies w/ 0 decimals, 0 value.
    worthless = '\n\n====\n\n'.join(
        f"{table}\n\n{sub}\n\n{tot}"
        for _,table,sub,tot in Invoice(
            [
                line
                for line,_ in line_amounts
                if line.currency in ("ZEENUS", )
            ],
            currencies	= ["HOT", "ETH", "BTC", "USD"],
            accounts	= accounts,
            conversions	= dict( conversions ),
        ).tables()
    )
    print( worthless )
    assert worthless == """\
|   Line | Description   |   Units |   Price | Tax %   |   Taxes |    Net |   Amount | Currency   | Symbol   |   Total BTC |   Total ETH |   Total HOT |   Total USDC |   Total WBTC |   Total WETH |   Total XRP |   Taxes BTC |   Taxes ETH |   Taxes HOT |   Taxes USDC |   Taxes WBTC |   Taxes WETH |   Taxes XRP |
|--------+---------------+---------+---------+---------+---------+--------+----------+------------+----------+-------------+-------------+-------------+--------------+--------------+--------------+-------------+-------------+-------------+-------------+--------------+--------------+--------------+-------------|
|      0 | Worthless     |       1 |  12,346 | no tax  |       0 | 12,346 |   12,346 | ZEENUS     | ZEENUS   |           0 |           0 |           0 |            0 |            0 |            0 |           0 |           0 |           0 |           0 |            0 |            0 |            0 |           0 |

| Account                                         | Crypto   | Currency      |   Subtotal 1/1 |   Subtotal 1/1 Taxes |
|-------------------------------------------------+----------+---------------+----------------+----------------------|
| BTC: bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2 | BTC      | Wrapped BTC   |              0 |                    0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | ETH      | Wrapped Ether |              0 |                    0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | HOT      | HoloToken     |              0 |                    0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | USDC     | USD Coin      |              0 |                    0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | WBTC     | Wrapped BTC   |              0 |                    0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | WETH     | Wrapped Ether |              0 |                    0 |
| XRP: rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV         | XRP      | XRP           |              0 |                    0 |

| Account                                         | Crypto   | Currency      |   Total 1/1 |   Total 1/1 Taxes |
|-------------------------------------------------+----------+---------------+-------------+-------------------|
| BTC: bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2 | BTC      | Wrapped BTC   |           0 |                 0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | ETH      | Wrapped Ether |           0 |                 0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | HOT      | HoloToken     |           0 |                 0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | USDC     | USD Coin      |           0 |                 0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | WBTC     | Wrapped BTC   |           0 |                 0 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | WETH     | Wrapped Ether |           0 |                 0 |
| XRP: rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV         | XRP      | XRP           |           0 |                 0 |"""  # noqa: E501

    # No conversions of non-0 values; default Invoice currency is USD.  Longest digits should be 2
    # Instead of querying BTC, ETH prices, provide a conversion (so our invoice pricing is static)
    shorter = '\n\n====\n\n'.join(
        f"{table}\n\n{sub}\n\n{tot}"
        for _,table,sub,tot in Invoice(
            [
                line
                for line,_ in line_amounts
                if line.currency in ("ZEENUS", None) or line.currency.upper().startswith( 'US' )
            ],
            accounts	= [
                account( SEED_ZOOS, crypto='Ethereum' ),
            ],
            conversions	= dict( conversions ) | {
                (eth,usd): 1500 for eth in ("ETH","WETH") for usd in ("USDC",)
            } | {
                (btc,eth): 15 for eth in ("ETH","WETH") for btc in ("BTC","WBTC")
            },
        ).tables()
    )
    print( shorter )
    assert shorter == """\
|   Line | Description           |   Units |     Price | Tax %    |   Taxes |       Net |    Amount | Currency   | Symbol   |   Total ETH |   Total USDC |   Total WETH |   Taxes ETH |   Taxes USDC |   Taxes WETH |
|--------+-----------------------+---------+-----------+----------+---------+-----------+-----------+------------+----------+-------------+--------------+--------------+-------------+--------------+--------------|
|      0 | Widgets for the Thing |     198 |      2.01 | 5% added |   19.90 |    397.98 |    417.88 | US Dollar  | USDC     |        0.28 |       417.88 |         0.28 |        0.01 |        19.90 |         0.01 |
|      1 | Worthless             |       1 | 12,345.68 | no tax   |    0.00 | 12,346.00 | 12,346.00 | ZEENUS     | ZEENUS   |        0.28 |       417.88 |         0.28 |        0.01 |        19.90 |         0.01 |
|      2 | Simple                |       1 | 12,345.68 | no tax   |    0.00 | 12,345.68 | 12,345.68 | USD        | USDC     |        8.51 |    12,763.56 |         8.51 |        0.01 |        19.90 |         0.01 |

| Account                                         | Crypto   | Currency      |   Subtotal 1/1 |   Subtotal 1/1 Taxes |
|-------------------------------------------------+----------+---------------+----------------+----------------------|
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | ETH      | Wrapped Ether |        8.50904 |             0.013267 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | USDC     | USD Coin      |   12,763.6     |            19.9      |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | WETH     | Wrapped Ether |        8.50904 |             0.013267 |

| Account                                         | Crypto   | Currency      |    Total 1/1 |   Total 1/1 Taxes |
|-------------------------------------------------+----------+---------------+--------------+-------------------|
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | ETH      | Wrapped Ether |      8.50904 |          0.013267 |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | USDC     | USD Coin      | 12,763.6     |         19.9      |
| ETH: 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | WETH     | Wrapped Ether |      8.50904 |          0.013267 |"""  # noqa: E501
