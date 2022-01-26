import json

import shamir_mnemonic

from .api		import account, create, addresses, addressgroups, accountgroups
from .recovery		import recover

from .dependency_test	import substitute, nonrandom_bytes, SEED_XMAS


def test_account():
    acct			= account( SEED_XMAS )
    assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'
    assert acct.path == "m/44'/60'/0'/0/0"

    acct			= account( SEED_XMAS, path="m/44'/60'/0'/0/1" )
    assert acct.address == '0x3b774e485fC818F0f377FBA657dfbF92B46f8504'
    assert acct.path == "m/44'/60'/0'/0/1"

    acct			= account( SEED_XMAS, crypto='Bitcoin' )
    assert acct.address == 'bc1qz6kp20ukkyx8c5t4nwac6g8hsdc5tdkxhektrt'
    assert acct.path == "m/84'/0'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Bitcoin', format='Legacy' )
    assert acct.address == '19FQ983heQEBXmopVNyJKf93XG7pN7sNFa'
    assert acct.path == "m/44'/0'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Bitcoin', format='SegWit' )
    assert acct.address == '3HxUpD7E8Y31vDDgDq1VFdNXWViAgBjYJe'
    assert acct.path == "m/44'/0'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Litecoin' )
    assert acct.address == 'ltc1qfjepkelqd3jx4e73s7p79lls6kqvvmak5pxy97'
    assert acct.path == "m/84'/2'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Litecoin', format='Legacy' )
    assert acct.address == 'LeyK1dbc5qKdKC9TvkygMTeoHixR3z1XG3'
    assert acct.path == "m/44'/2'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Litecoin', format='SegWit' )
    assert acct.address == 'MPULjvY9dNjpNkgbwhfJtD7N6Lbfam1XsP'
    assert acct.path == "m/44'/2'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Dogecoin' )
    assert acct.address == 'DQCnF49GwQ5auL3u5c2uow62XS57RCA2r1'
    assert acct.path == "m/44'/3'/0'/0/0"


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_create():
    details			= create(
        "SLIP39 Wallet: Test",
        1,
        dict( fren = (3,5) ),
        SEED_XMAS
    )

    assert details.groups == {
        "fren": ( 3, [
            "academic acid academic acne academic academic academic academic academic academic academic academic academic academic academic academic academic carpet making building",
            "academic acid academic agree depart dance galaxy acrobat mayor disaster quick justice ordinary agency plunge should pupal emphasis security obtain",
            "academic acid academic amazing crush royal faint spit briefing craft floral negative work depend prune adapt merit romp home elevator",
            "academic acid academic arcade cargo unfold aunt spider muscle bedroom triumph theory gather dilemma building similar chemical object cinema salon",
            "academic acid academic axle crush swing purple violence teacher curly total equation clock mailman display husband tendency smug laundry disaster"
        ] ),
    }

    assert len(details.accounts) == 1
    [(eth,btc)] = details.accounts  # The default accounts created are ETH, BTC
    assert eth.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'
    assert btc.address == 'bc1qz6kp20ukkyx8c5t4nwac6g8hsdc5tdkxhektrt'

    assert recover( details.groups['fren'][1][:3] ) == SEED_XMAS


def test_addresses():
    master_secret		= b'\xFF' * 16
    addrs			= list( addresses(
        master_secret	= master_secret,
        crypto		= 'ETH',
        paths		= ".../-9",
    ))
    # print( json.dumps( addrs, indent=4, default=str ))
    assert addrs == [
        (
            "ETH",
            "m/44'/60'/0'/0/0",
            "0x824b174803e688dE39aF5B3D7Cd39bE6515A19a1"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/1",
            "0x8D342083549C635C0494d3c77567860ee7456963"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/2",
            "0x52787E24965E1aBd691df77827A3CfA90f0166AA"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/3",
            "0xc2442382Ae70c77d6B6840EC6637dB2422E1D44e"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/4",
            "0x42a910D380dE132B5227e3277Cc70C3C76a884aC"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/5",
            "0x1A3db5E0422c78F43a35686f0307Da8f22344dE0"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/6",
            "0x19031c515C5d91DB7988D89AAA6F71a5825f5245"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/7",
            "0xaE693156ac600f5B0D58e5090ecf0A578c5Cc0a8"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/8",
            "0x4347541fa648BCE62543a8AbC2901E08017f6A6a"
        ),
        (
            "ETH",
            "m/44'/60'/0'/0/9",
            "0xC11235559Dd4c5224a19396C3A14526E92ebba35"
        )
    ]
    addrs			= list( addresses(
        master_secret	= master_secret,
        crypto		= 'BTC',
        paths		= '.../0/-2',
        format		= 'Bech32',
    ))
    print( json.dumps( addrs, indent=4, default=str ))
    assert addrs == [
        (
            "BTC",
            "m/84'/0'/0'/0/0",
            "bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl"
        ),
        (
            "BTC",
            "m/84'/0'/0'/0/1",
            "bc1qnec684yvuhfrmy3q856gydllsc54p2tx9w955c"
        ),
        (
            "BTC",
            "m/84'/0'/0'/0/2",
            "bc1q2snj0zcg23dvjpw7m9lxtu0ap0hfl5tlddq07j"
        ),
    ]


def test_addressgroups():
    master_secret		= b'\xFF' * 16
    addrgrps			= list( enumerate( addressgroups(
        master_secret	= master_secret,
        cryptopaths	= [
            ('ETH', ".../-3"),
            ('BTC', ".../-3"),
            ('LTC', ".../-3"),
            ('Doge', ".../-3"),
        ],
    )))
    # print( addrgrps )
    assert addrgrps == [
        (0, (("ETH", "m/44'/60'/0'/0/0", "0x824b174803e688dE39aF5B3D7Cd39bE6515A19a1"),
             ("BTC", "m/84'/0'/0'/0/0", "bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl"),
             ('LTC', "m/84'/2'/0'/0/0", 'ltc1qe5m2mst9kjcqtfpapaanaty40qe8xtusmq4ake'),
             ('DOGE', "m/44'/3'/0'/0/0", 'DN8PNN3dipSJpLmyxtGe4EJH38EhqF8Sfy'))),
        (1, (("ETH", "m/44'/60'/0'/0/1", "0x8D342083549C635C0494d3c77567860ee7456963"),
             ("BTC", "m/84'/0'/0'/0/1", "bc1qnec684yvuhfrmy3q856gydllsc54p2tx9w955c"),
             ('LTC', "m/84'/2'/0'/0/1", 'ltc1qm0hwvvk28wlyfu3sed66e9yyvmwm35xtfexva3'),
             ('DOGE', "m/44'/3'/0'/0/1",'DJYE9WWaCA1CbV9x23qkcgNX7Yr9YjCebA'))),
        (2, (("ETH", "m/44'/60'/0'/0/2", "0x52787E24965E1aBd691df77827A3CfA90f0166AA"),
             ("BTC", "m/84'/0'/0'/0/2", "bc1q2snj0zcg23dvjpw7m9lxtu0ap0hfl5tlddq07j"),
             ('LTC', "m/84'/2'/0'/0/2", 'ltc1qx3r3efsmupn34gmwu25fu39tn4h79cjfwvlpfu'),
             ('DOGE', "m/44'/3'/0'/0/2",'DQfJcJzLFW9LJPJXNkLeq1WqPfLsRq47Jj'))),
        (3, (("ETH", "m/44'/60'/0'/0/3", "0xc2442382Ae70c77d6B6840EC6637dB2422E1D44e"),
             ("BTC", "m/84'/0'/0'/0/3", "bc1qxwekjd46aa5n0s3dtsynvtsjwsne7c5f5w5dsd"),
             ('LTC', "m/84'/2'/0'/0/3", 'ltc1qnqzyear8kct0yjzupe2pxtq0mwee5kl642mj78'),
             ('DOGE', "m/44'/3'/0'/0/3", 'DLVPiM5763cyNJfoa13cv4kV3b87FgVMCS'))),
    ]


def test_accountgroups():
    master_secret		= b'\xFF' * 16
    acctgrps			= list( accountgroups(
        master_secret	= master_secret,
        cryptopaths	= [
            ('ETH', ".../-3"),
            ('BTC', ".../-3"),
        ],
    ))
    # print( json.dumps( acctgrps, default=repr ))
    assert len(acctgrps) == 4
