import shamir_mnemonic

from .api		import account, create, addresses, addressgroups, accountgroups
from .recovery		import recover

from .dependency_test	import substitute, nonrandom_bytes, SEED_XMAS


def test_account():
    acct			= account( SEED_XMAS )
    assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'


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
    assert btc.address == '19FQ983heQEBXmopVNyJKf93XG7pN7sNFa'

    assert recover( details.groups['fren'][1][:3] ) == SEED_XMAS


def test_addresses():
    master_secret		= b'\xFF' * 16
    addrs			= list( addresses(
        master_secret	= master_secret,
        crypto		= 'ETH',
        paths		= "m/44'/60'/0'/0/-9",
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
    ))
    # print( json.dumps( addrs, indent=4, default=str ))
    assert addrs == [
        (
            "BTC",
            "m/44'/0'/0'/0/0",
            "1MAjc529bjmkC1iCXTw2XMHL2zof5StqdQ"
        )
    ]


def test_addressgroups():
    master_secret		= b'\xFF' * 16
    addrgrps			= list( enumerate( addressgroups(
        master_secret	= master_secret,
        cryptopaths	= [
            ('ETH', "m/44'/60'/0'/0/-3"),
            ('BTC', "m/44'/0'/0'/0/-3"),
        ],
    )))
    # print( addrgrps )
    assert addrgrps == [
        (0, (("ETH", "m/44'/60'/0'/0/0", "0x824b174803e688dE39aF5B3D7Cd39bE6515A19a1"), ("BTC", "m/44'/0'/0'/0/0", "1MAjc529bjmkC1iCXTw2XMHL2zof5StqdQ"))),
        (1, (("ETH", "m/44'/60'/0'/0/1", "0x8D342083549C635C0494d3c77567860ee7456963"), ("BTC", "m/44'/0'/0'/0/1", "1BGwDuVPJeXDG9upaHvVPds5MXwkTjZoav"))),
        (2, (("ETH", "m/44'/60'/0'/0/2", "0x52787E24965E1aBd691df77827A3CfA90f0166AA"), ("BTC", "m/44'/0'/0'/0/2", "1L64uW2jKB3d1mWvfzTGwZPTGg9qPCaQFM"))),
        (3, (("ETH", "m/44'/60'/0'/0/3", "0xc2442382Ae70c77d6B6840EC6637dB2422E1D44e"), ("BTC", "m/44'/0'/0'/0/3", "1NQv8w7ZNPTadaJg1KxWTC84kLMnCp6pLR"))),
    ]


def test_accountgroups():
    master_secret		= b'\xFF' * 16
    acctgrps			= list( accountgroups(
        master_secret	= master_secret,
        cryptopaths	= [
            ('ETH', "m/44'/60'/0'/0/-3"),
            ('BTC', "m/44'/0'/0'/0/-3"),
        ],
    ))
    # print( json.dumps( acctgrps, default=repr ))
    assert len(acctgrps) == 4
