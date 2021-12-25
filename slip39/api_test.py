import codecs

import pytest
import shamir_mnemonic

from .generate_test	import substitute, nonrandom_bytes
from .generate		import account, create
from .recovery		import recover

SEED_XMAS_HEX			= b"dd0e2f02b1f6c92a1a265561bc164135"
SEED_XMAS			= codecs.decode( SEED_XMAS_HEX, 'hex_codec' )


def test_account():
    acct			= account( SEED_XMAS )
    assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_create():
    details			= create(
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


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_recover():
    details			= create(
        "recovery test", 2, dict( one = (1,1), two = (1,1), fam = (2,4), fren = (3,5) ), SEED_XMAS
    )
    #import json
    #print( json.dumps( details.groups, indent=4 ))
    assert details.groups == {
        "one": (
            1,
            [
                "academic acid acrobat romp chubby client grief judicial pulse domain flip elevator become spirit heat patent hawk remove pickup boring"
            ]
        ),
        "two": (
            1,
            [
                "academic acid beard romp away ancient domain jacket early admit true disaster manual sniff seafood guest stick grumpy blessing unknown"
            ]
        ),
        "fam": (
            2,
            [
                "academic acid ceramic roster density snapshot crush modify born plastic greatest victim merit weapon general cover wits cradle quick emphasis",
                "academic acid ceramic scared brother carve scout stay repeat that fumes tendency junior clay freshman rhyme infant enlarge puny decent",
                "academic acid ceramic shadow class findings zero blessing sidewalk drink jump hormone advocate flip install alpha ugly speak prospect solution",
                "academic acid ceramic sister aluminum obesity blue furl grownup island educate junk traveler listen evidence merit grant python purchase piece"
            ]
        ),
        "fren": (
            3,
            [
                "academic acid decision round academic academic academic academic academic academic academic academic academic academic academic academic academic ranked flame amount",
                "academic acid decision scatter change pleasure dive cricket class impulse lungs hour invasion strike mustang friendly divorce corner penalty fawn",
                "academic acid decision shaft disaster python expand math typical screw rumor research unusual segment install curly debut shadow orange museum",
                "academic acid decision skin browser breathe intimate picture smirk railroad equip spirit nervous capital teaspoon hybrid angel findings hunting similar",
                "academic acid decision snake angel phrase gums response tracks carve secret bucket liquid dictate enemy decrease dance early weapon season"
            ]
        )
    }
    recover( details.groups['one'][1] + details.groups['fren'][1][:3] ) == SEED_XMAS

    # Enough correct number of mnemonics must be provided (extras ignored)
    with pytest.raises(shamir_mnemonic.MnemonicError) as excinfo:
        recover( details.groups['one'][1] + details.groups['fren'][1][:2] )
    assert "Wrong number of mnemonics" in str(excinfo.value)

    recover( details.groups['one'][1] + details.groups['fren'][1][:4] ) == SEED_XMAS

    # Invalid mnemonic phrases are rejected (one word changed)
    with pytest.raises(shamir_mnemonic.MnemonicError) as excinfo:
        recover( details.groups['one'][1] + details.groups['fren'][1][:2] + [
            "academic acid academic axle crush swing purple violence teacher curly total equation clock mailman display husband tendency smug laundry laundry"
        ])
    assert "Invalid mnemonic checksum" in str(excinfo.value)

    # Duplicate mnemonics rejected/ignored
    with pytest.raises(shamir_mnemonic.MnemonicError) as excinfo:
        recover( details.groups['one'][1] + details.groups['fren'][1][:2] + details.groups['fren'][1][:1] )
    assert "Wrong number of mnemonics" in str(excinfo.value)

    # Mnemonics from another SLIP-39 rejected
    with pytest.raises(shamir_mnemonic.MnemonicError) as excinfo:
        recover( details.groups['one'][1] + details.groups['fren'][1][:2] + [
            "academic acid academic axle crush swing purple violence teacher curly total equation clock mailman display husband tendency smug laundry disaster"
        ])
    assert "Invalid set of mnemonics" in str(excinfo.value)
