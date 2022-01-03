import codecs
import contextlib
import json
import pytest

from eth_account.hdaccount.mnemonic import Mnemonic

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


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
@pytest.mark.parametrize("entropy,expected_BIP39,expected_seed,expected_SLIP39", [
    (
        "00000000000000000000000000000000",
        "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
        "c55257c360c07c72029aebc1b53c05ed0362ada38ead3e3e9efa3708e53495531f09a6987599d18264c1e1c92f2cf141630c7a3c4ab7c81b2f001698e7463b04",
        "academic acid acrobat romp academic facility filter scared decision likely luxury acid aquatic campus submit cleanup style repair taste"
        " funding rebuild exotic busy perfect research curly snake exact seafood geology necklace axle fatigue valuable amuse spray pile union"
        " blue switch parking repeat pumps trend cleanup nuclear breathe guitar jacket party home science recover apart render artwork lair ambition market",
    ),
    (
        "7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f7f",
        "legal winner thank year wave sausage worth useful legal winner thank yellow",
        "2e8905819b8723fe2c1d161860e5ee1830318dbf49a83bd451cfb8440c28bd6fa457fe1296106559a3c80937a1c1069be3a3a5bd381ee6260e8d9739fce1f607",
        "academic acid acrobat romp acquire home transfer threaten year remove laundry editor midst climate research observe safari deadline staff"
        " twin downtown cause suitable airport total downtown image boundary tracks hospital brother squeeze phrase webcam grief deploy garbage climate"
        " lawsuit headset license aluminum hawk bedroom evidence thumb thorn shrimp finger easy exercise wisdom warn axis timber paper salon harvest luck",
    ),
])
def test_bip39( entropy, expected_BIP39, expected_seed, expected_SLIP39 ):

    # Generate a BIP39 Mnemonic seed.  This is a one-way process; a BIP39 Mnemonic (and its
    # originating Entropy) is *not* recoverable from the Seed, as the derivation function is not
    # reversible.  The process is Entropy --> BIP39 Mnemonic --> Seed
    m = Mnemonic("english")
    mnemonic = m.to_mnemonic(bytes.fromhex(entropy))
    assert m.is_mnemonic_valid(mnemonic)
    assert mnemonic == expected_BIP39

    seed = Mnemonic.to_seed(mnemonic, passphrase="TREZOR")
    assert seed.hex() == expected_seed

    # Now that we have the desired seed from the BIP39 process, we *can* save the 512-bit Seed via a
    # (large) SLIP39 Mnemonic.

    mnemonics			= shamir_mnemonic.generate_mnemonics(
        group_threshold	= 2,
        groups		= [(1, 1), (1, 1), (2, 5), (3, 6)],
        master_secret	= seed,
        passphrase	= b"",
    )

    print( json.dumps( mnemonics, indent=4 ))
    assert len( mnemonics ) == 4
    assert shamir_mnemonic.combine_mnemonics(mnemonics[0] + mnemonics[2][0:2]) \
        == shamir_mnemonic.combine_mnemonics(mnemonics[1] + mnemonics[2][2:4]) \
        == seed
    assert all( len( m.split(' ')) == 59 for g in mnemonics for m in g )
    assert any( m == expected_SLIP39     for g in mnemonics for m in g )
