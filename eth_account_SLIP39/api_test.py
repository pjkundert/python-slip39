import codecs
import contextlib
import json

import eth_account
import shamir_mnemonic

from .generate_test	import substitute, nonrandom_bytes
from .generate		import PATH_ETH_DEFAULT, account, create, recover

SEED_XMAS_HEX			= b"dd0e2f02b1f6c92a1a265561bc164135"
SEED_XMAS			= codecs.decode( SEED_XMAS_HEX, 'hex_codec' )


def test_account():
    acct			= account( SEED_XMAS )
    assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_create():
    (mnem,acct)			= create( 1, [(3,5)], SEED_XMAS )
    #print( json.dumps( mnem, indent=4 ))
    assert len( mnem ) == 1 and len( mnem[0] ) == 5
    assert mnem == [
        [
            "academic acid academic acne academic academic academic academic academic academic academic academic academic academic academic academic academic carpet making building",
            "academic acid academic agree depart dance galaxy acrobat mayor disaster quick justice ordinary agency plunge should pupal emphasis security obtain",
            "academic acid academic amazing crush royal faint spit briefing craft floral negative work depend prune adapt merit romp home elevator",
            "academic acid academic arcade cargo unfold aunt spider muscle bedroom triumph theory gather dilemma building similar chemical object cinema salon",
            "academic acid academic axle crush swing purple violence teacher curly total equation clock mailman display husband tendency smug laundry disaster"
        ]
    ]
    print( json.dumps( dict( (k,getattr( acct, k ))
                             for k in dir( acct )
                             if not k.startswith('_')
                             ),
                       indent=4, default=str ))
    assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'

    assert recover( mnem[0][:3] ) == SEED_XMAS
