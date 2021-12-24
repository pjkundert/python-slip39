import codecs
import contextlib
#import json

import shamir_mnemonic

SEED_KNOWN_HEX			= b'87e39270d1d1976e9ade9cc15a084c62'
SEED_KNOWN			= codecs.decode( SEED_KNOWN_HEX, 'hex_codec' )
PASS_KNOWN			= b''

SEED_TREZOR			= b"ABCDEFGHIJKLMNOP"
PASS_TREZOR			= b"TREZOR"


class substitute( contextlib.ContextDecorator ):
    """The SLIP-39 standard includes random data in portions of the as share.  Replace the random
    function during testing to get determinism in resultant nmenomics.

    """
    def __init__( self, thing, attribute, value ):
        self.thing		= thing
        self.attribute		= attribute
        self.value		= value
        self.saved		= None

    def __enter__( self ):
        self.saved		= getattr( self.thing, self.attribute )
        setattr( self.thing, self.attribute, self.value )

    def __exit__( self, *exc ):
        setattr( self.thing, self.attribute, self.saved )


def nonrandom_bytes( n ):
    return b'\0' * n


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_share_1_of_3_5():
    mnemonics			= shamir_mnemonic.generate_mnemonics(
        group_threshold	= 1,
        groups		= [(3, 5)],
        master_secret	= SEED_TREZOR,
        passphrase	= PASS_TREZOR,
    )

    #print( json.dumps( mnemonics, indent=4 ))
    assert shamir_mnemonic.combine_mnemonics(mnemonics[0][:3]) \
        == shamir_mnemonic.combine_mnemonics(mnemonics[0][2:])
    assert mnemonics[0][0] == "academic acid academic acne academic academic academic academic academic academic academic academic academic academic academic academic academic carpet making building"
    assert mnemonics[0][1] == "academic acid academic agree artist uncover slavery vocal airport sharp explain violence enlarge minister dragon soul wrist much valid pencil"


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_share_2_of_groups():
    mnemonics		= shamir_mnemonic.generate_mnemonics(
        group_threshold	= 2,
        groups		= [(1, 1), (1, 1), (2, 5), (3, 6)],
        master_secret	= SEED_KNOWN,
        passphrase	= PASS_KNOWN,
    )

    #print( json.dumps( mnemonics, indent=4 ))
    assert len( mnemonics ) == 4
    assert shamir_mnemonic.combine_mnemonics(mnemonics[0] + mnemonics[2][0:2]) \
        == shamir_mnemonic.combine_mnemonics(mnemonics[1] + mnemonics[2][2:4])
    assert mnemonics[2][0] == "academic acid ceramic roster academic photo daisy indicate salary hunting fancy guest taste diploma express usher regret equip install prevent"
    assert mnemonics[2][1] == "academic acid ceramic scared cubic episode metric intend symbolic overall employer course kind human criminal width game duration maiden favorite"
