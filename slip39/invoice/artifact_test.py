import json

from fractions		import Fraction
from pathlib		import Path

import pytest

import tabulate

from crypto_licensing.misc import parse_datetime

from ..api		import account
from .artifact		import LineItem, Invoice, conversions_remaining, conversions_table, Contact, produce_invoice

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
| Coin   | in BTC   | in ETH   |    in USD |
|--------+----------+----------+-----------|
| BTC    |          | ?        | 23,456.78 |
| ETH    |          |          |  1,234.56 |
| USD    |          |          |           |"""

    c_simple			= dict( c1 )
    c_simple_i			= 0
    while ( conversions_remaining( c_simple )):
        c_simple_i	       += 1
    assert c_simple_i == 2
    c_simple_tbl		= conversions_table( c_simple )
    print( c_simple_tbl )
    assert c_simple_tbl == """\
| Coin   |      in BTC |    in ETH |    in USD |
|--------+-------------+-----------+-----------|
| BTC    |             | 19.000113 | 23,456.78 |
| ETH    | 0.052631265 |           |  1,234.56 |
| USD    |             |           |           |"""

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
| Coin   | in BTC   |        in DOGE |    in ETH |    in USD |
|--------+----------+----------------+-----------+-----------|
| BTC    |          | 259,740.26     | 19.000113 | 23,456.78 |
| DOGE   |          |                |           |           |
| ETH    |          |  13,670.458    |           |  1,234.56 |
| USD    |          |      11.073142 |           |           |"""

    c_w_doge_all		= conversions_table( c_w_doge, greater=False )
    print( c_w_doge_all )
    assert c_w_doge_all == """\
| Coin   |        in BTC |        in DOGE |         in ETH |           in USD |
|--------+---------------+----------------+----------------+------------------|
| BTC    |               | 259,740.26     | 19.000113      | 23,456.78        |
| DOGE   | 3.85e-06      |                |  7.3150437e-05 |      0.090308603 |
| ETH    | 0.052631265   |  13,670.458    |                |  1,234.56        |
| USD    | 4.2631597e-05 |      11.073142 |  0.00081000518 |                  |"""

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
            price	= Fraction( 201, 100000 ),
            tax		= Fraction( 5, 100 ),  # exclusive
            currency	= 'ETH',
        ),
        ( 527.625, 25.125, "5% added" ),
    ], [
        LineItem(
            description	= "Something else, very detailed and elaborate to explain",
            units	= 100,
            price	= Fraction( 201, 100000 ),
            tax		= Fraction( 105, 100 ),  # inclusive
            decimals	= 8,
            currency	= 'Bitcoin',
        ),
        ( 2.01, 0.09571, "5% incl." ),
    ], [
        LineItem(
            description	= "Buy some Holo hosting",
            units	= 12,
            price	= 12345.6,
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


def test_tabulate( tmp_path ):
    accounts			= [
        account( SEED_ZOOS, crypto='Ripple' ),
        account( SEED_ZOOS, crypto='Ethereum' ),
        account( SEED_ZOOS, crypto='Bitcoin' ),
    ]
    conversions			= {
        ("BTC","XRP"): 60000,
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
        columns=('#', 'Description', 'Qty', 'Currency', 'Coin', 'Price', 'Tax %', 'Taxes', 'Amount', 'Total USDC'),
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
| Description                                |   Qty |   Price | Tax %   |   Taxes |   Amount | Coin   |
|--------------------------------------------+-------+---------+---------+---------+----------+--------|
| Worthless                                  |     1 |  12,346 | no tax  |       0 |   12,346 | ZEENUS |
|--------------------------------------------+-------+---------+---------+---------+----------+--------|
| bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2 |       |         |         |       0 |        0 | BTC    |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       |         |         |       0 |        0 | ETH    |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       |         |         |       0 |        0 | HOT    |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       |         |         |       0 |        0 | USDC   |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       |         |         |       0 |        0 | WBTC   |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       |         |         |       0 |        0 | WETH   |
| rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV         |       |         |         |       0 |        0 | XRP    |

| Account                                    |   Taxes |   Subtotal | Coin   | Currency      |
|--------------------------------------------+---------+------------+--------+---------------|
| bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2 |       0 |          0 | BTC    | Bitcoin       |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |          0 | ETH    | Ethereum      |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |          0 | HOT    | HoloToken     |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |          0 | USDC   | USD Coin      |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |          0 | WBTC   | Wrapped BTC   |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |          0 | WETH   | Wrapped Ether |
| rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV         |       0 |          0 | XRP    | Ripple        |

| Account                                    |   Taxes |   Total | Coin   | Currency      |
|--------------------------------------------+---------+---------+--------+---------------|
| bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2 |       0 |       0 | BTC    | Bitcoin       |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |       0 | ETH    | Ethereum      |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |       0 | HOT    | HoloToken     |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |       0 | USDC   | USD Coin      |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |       0 | WBTC   | Wrapped BTC   |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       0 |       0 | WETH   | Wrapped Ether |
| rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV         |       0 |       0 | XRP    | Ripple        |"""  # noqa: E501

    # No conversions of non-0 values; default Invoice currency is USD.  Longest digits should be 2
    # Instead of querying BTC, ETH prices, provide a conversion (so our invoice pricing is static)
    shorter_invoice		= Invoice(
        [
            line
            for line,_ in line_amounts
            if line.currency in ("ZEENUS", None) or line.currency.upper().startswith( 'US' )
        ],
        accounts	= accounts,
        conversions	= dict( conversions ) | {
            (eth,usd): 1500 for eth in ("ETH","WETH") for usd in ("USDC",)
        } | {
            (btc,eth): 15 for eth in ("ETH","WETH") for btc in ("BTC","WBTC")
        },
    )
    # Include some selected columns
    shorter = '\n\n====\n\n'.join(
        f"{table}\n\n{sub}\n\n{tot}"
        for _,table,sub,tot in shorter_invoice.tables(
            columns=('#', 'Description', 'Qty', 'Currency', 'Coin', 'Price', 'Tax %', 'Taxes', 'Amount', 'Total USDC'),
        )
    )
    print( shorter )
    assert shorter == """\
|   # | Description                                |   Qty | Currency      | Coin   |     Price | Tax %    |       Taxes |        Amount |   Total USDC |
|-----+--------------------------------------------+-------+---------------+--------+-----------+----------+-------------+---------------+--------------|
|   0 | Widgets for the Thing                      |   198 | US Dollar     | USDC   |      2.01 | 5% added | 19.9        |    417.88     |       417.88 |
|   1 | Worthless                                  |     1 | ZEENUS        | ZEENUS | 12,346    | no tax   |  0          | 12,346        |       417.88 |
|   2 | Simple                                     |     1 | USD           | USDC   | 12,345.7  | no tax   |  0          | 12,345.7      |    12,763.6  |
|-----+--------------------------------------------+-------+---------------+--------+-----------+----------+-------------+---------------+--------------|
|     | bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2 |       | Bitcoin       | BTC    |           |          |  0.00088444 |      0.567269 |              |
|     | 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       | Ethereum      | ETH    |           |          |  0.013267   |      8.50904  |              |
|     | 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       | USD Coin      | USDC   |           |          | 19.9        | 12,763.6      |              |
|     | 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       | Wrapped BTC   | WBTC   |           |          |  0.00088444 |      0.567269 |              |
|     | 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |       | Wrapped Ether | WETH   |           |          |  0.013267   |      8.50904  |              |
|     | rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV         |       | Ripple        | XRP    |           |          | 53.07       | 34,036.2      |              |

| Account                                    |       Taxes |      Subtotal | Coin   | Currency      |
|--------------------------------------------+-------------+---------------+--------+---------------|
| bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2 |  0.00088444 |      0.567269 | BTC    | Bitcoin       |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |  0.013267   |      8.50904  | ETH    | Ethereum      |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | 19.9        | 12,763.6      | USDC   | USD Coin      |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |  0.00088444 |      0.567269 | WBTC   | Wrapped BTC   |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |  0.013267   |      8.50904  | WETH   | Wrapped Ether |
| rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV         | 53.07       | 34,036.2      | XRP    | Ripple        |

| Account                                    |       Taxes |         Total | Coin   | Currency      |
|--------------------------------------------+-------------+---------------+--------+---------------|
| bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2 |  0.00088444 |      0.567269 | BTC    | Bitcoin       |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |  0.013267   |      8.50904  | ETH    | Ethereum      |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E | 19.9        | 12,763.6      | USDC   | USD Coin      |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |  0.00088444 |      0.567269 | WBTC   | Wrapped BTC   |
| 0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E |  0.013267   |      8.50904  | WETH   | Wrapped Ether |
| rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV         | 53.07       | 34,036.2      | XRP    | Ripple        |"""  # noqa: E501

    this			= Path( __file__ ).resolve()
    test			= this.with_suffix( '' )
    # here			= this.parent

    inv_date			= parse_datetime( "2021-01-01 00:00:00.1 Canada/Pacific" )

    vendor			= Contact(
        name	= "Dominion Research & Development Corp.",
        contact	= "Perry Kundert <perry@dominionrnd.com>",
        phone	= "+1-780-970-8148",
        address	= """\
275040 HWY 604
Lacombe, AB  T4L 2N3
CANADA
""",
        billing	= """\
RR#3, Site 1, Box 13
Lacombe, AB  T4L 2N3
CANADA
""",
    )
    client			= Contact(
        name	= "Awesome, Inc.",
        contact	= "Great Guy <perry+awesome@dominionrnd.com>",
        address	= """\
123 Awesome Ave.
Schenectady, NY  12345
USA
""",
    )

    (paper_format,orientation),pdf,metadata = produce_invoice(
        invoice		= shorter_invoice,
        inv_date	= inv_date,
        vendor		= vendor,
        client		= client,
        directory	= test,
        #inv_image	= 'dominionrnd-invoice.png',    # Full page background image
        inv_logo	= 'dominionrnd-logo.png',       # Logo 16/9 in bottom right of header
        inv_label	= 'Quote',
    )

    print( f"Invoice metadata: {metadata}" )
    temp		= Path( tmp_path )
    path		= temp / 'invoice-shorter.pdf'
    pdf.output( path )
    print( f"Invoice saved: {path}" )

    # Finally, generate invoice with all rows, and all conversions from blockchain Oracle (except
    # XRP, for which we do not have an oracle, so must provide an estimate from another source...)
    complete_invoice		= Invoice(
        [
            line
            for line,_ in line_amounts
        ],
        currencies	= ["HOT", "ETH", "BTC", "USD"],
        accounts	= accounts,
        conversions	= {
            ("BTC","XRP"): 60000,
        }
    )

    (paper_format,orientation),pdf,metadata = produce_invoice(
        invoice		= complete_invoice,
        inv_date	= inv_date,
        vendor		= vendor,
        client		= client,
        directory	= test,
        #inv_image	= 'dominionrnd-invoice.png',    # Full page background image
        inv_logo	= 'dominionrnd-logo.png',       # Logo 16/9 in bottom right of header
    )

    print( f"Invoice metadata: {metadata}" )
    temp		= Path( tmp_path )
    path		= temp / 'invoice-complete.pdf'
    pdf.output( path )
    print( f"Invoice saved: {path}" )
