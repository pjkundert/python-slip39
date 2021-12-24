import codecs

import shamir_mnemonic

from .generate_test	import substitute, nonrandom_bytes
from .generate		import account, create, recover

SEED_XMAS_HEX			= b"dd0e2f02b1f6c92a1a265561bc164135"
SEED_XMAS			= codecs.decode( SEED_XMAS_HEX, 'hex_codec' )


def test_account():
    acct			= account( SEED_XMAS )
    assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_create():
    details		= create(
        "SLIP39 Wallet: Test",
        1, dict( fren = (3,5) ), SEED_XMAS )

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
    for path,acct in details.accounts.items():
        assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'

    assert recover( details.groups['fren'][1][:3] ) == SEED_XMAS
