import base64
import cmath
import codecs
import csv
import hashlib
import itertools
import json
import logging
import math
import os
import pytest
import random
import secrets
import multiprocessing

from collections	import deque

import shamir_mnemonic

from .api		import create, account, path_hardened
from .recovery		import recover, recover_bip39, shannon_entropy, signal_entropy, analyze_entropy
from .recovery.entropy	import fft, ifft, pfft, dft, dft_on_real, dft_to_rms_mags, entropy_bin_dfts, denoise_mags, signal_draw, signal_recover_real, scan_entropy
from .dependency_test	import substitute, nonrandom_bytes, SEED_XMAS, SEED_ONES, SEED_ZERO
from .util		import avg, rms, ordinal, commas, round_onto

log				= logging.getLogger( __package__ )

groups_example			= dict( one = (1,1), two = (1,1), fam = (2,4), fren = (3,5) )

# Disable printing of details unless something goes wrong...
print_NOOP			= lambda *args, **kwds: None
print				= print_NOOP

def noise( mag ):
    return mag * ( random.random() * 2 - 1 )


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_recover():
    details			= create(
        "recovery test", 2, groups_example, SEED_XMAS
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
    assert recover( details.groups['one'][1] + details.groups['fren'][1][:3] ) == SEED_XMAS

    # Enough correct number of mnemonics must be provided (extras ignored)
    with pytest.raises(shamir_mnemonic.MnemonicError) as excinfo:
        recover( details.groups['one'][1] + details.groups['fren'][1][:2] )
    assert "Wrong number of mnemonics" in str(excinfo.value)

    assert recover( details.groups['one'][1] + details.groups['fren'][1][:4] ) == SEED_XMAS

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


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_recover_bip39():
    """Go through the 3 methods for producing accounts from the same 0xffff...ffff Seed Entropy."""

    # Get BIP-39 Seed generated from Mnemonic Entropy + passphrase
    bip39seed			= recover_bip39( 'zoo ' * 11 + 'wrong' )
    assert codecs.encode( bip39seed, 'hex_codec' ).decode( 'ascii' ) \
        == 'b6a6d8921942dd9806607ebc2750416b289adea669198769f2e15ed926c3aa92bf88ece232317b4ea463e84b0fcd3b53577812ee449ccc448eb45e6f544e25b6'
    details_bip39		= create(
        "bip39 recovery test", 2, groups_example, master_secret=bip39seed,
    )
    #import json
    #print( json.dumps( details_bip39.groups, indent=4 ))
    assert details_bip39.groups == {
        "one": (
            1,
            [
                "academic acid acrobat romp academic angel email prospect endorse strategy debris award strike frost actress facility legend safari pistol"
                " mouse hospital identify unwrap talent entrance trust cause ranked should impulse avoid fangs various radar dilemma indicate says rich work"
                " presence jerky glance hesitate huge depend tension loan tolerate news agree geology phrase random simple finger alarm depart inherit grin"
            ]
        ),
        "two": (
            1,
            [
                "academic acid beard romp acne floral cricket answer debris making decorate square withdraw empty decorate object artwork tracks rocky tolerate"
                " syndrome decorate predator sweater ordinary pecan plastic spew facility predator miracle change solution item lizard testify coal excuse lecture"
                " exercise hamster hand crystal rainbow indicate phantom require satisfy flame acrobat detect closet patent therapy overall muscle spill adjust unhappy"
            ]
        ),
        "fam": (
            2,
            [
                "academic acid ceramic roster acquire again tension ugly edge profile custody geology listen hazard smug branch adequate fishing simple adapt fancy"
                " hour method emperor tactics float quiet location satoshi guilt fantasy royal machine dictate squeeze devote oven eclipse writing level sheriff"
                " teacher purchase building veteran spirit woman realize width vanish scholar jewelry desktop stilt random rhyme debut premium theater",
                "academic acid ceramic scared acid space fantasy breathe true recover privacy tactics boring harvest punish swimming leader talent exchange diet"
                " enforce vanish volume organize coastal emperor change intend club scene intimate upgrade dragon burning lily huge market calcium forecast holiday"
                " merit method type ruler equip retailer pancake paces thorn worthy always story promise clock staff floral smart iris repair",
                "academic acid ceramic shadow acne rumor decent elder aspect lizard obesity friendly regular aircraft beyond military campus employer seafood cover"
                " ivory dough galaxy victim diminish average music cause behavior declare brave toxic visual academic include lilac repair morning rapids building"
                " kernel herald careful helpful move hawk flash glimpse seafood listen writing rocky browser change hybrid diet organize system wrote",
                "academic acid ceramic sister academic both legend raspy pecan mixed broken tenant critical again imply finance pacific single echo capital hesitate"
                " piece disease crush slush belong airline smug voice organize dryer standard emission curious charity swing pitch senior behavior vintage chemical"
                " cage editor rebuild costume adult ancestor erode steady makeup depart carpet level sympathy being soldier glimpse airport picture"
            ]
        ),
        "fren": (
            3,
            [
                "academic acid decision round academic academic academic academic academic academic academic academic academic academic academic academic academic"
                " academic academic academic academic academic academic academic academic academic academic academic academic academic academic academic academic"
                " academic academic academic academic academic academic academic academic academic academic academic academic academic academic academic academic"
                " academic academic academic academic academic academic academic aviation endless plastic",
                "academic acid decision scatter acid ugly raspy famous swimming else length gray raspy brother fake aunt auction premium military emphasis perfect"
                " surprise class suitable crunch famous burden military laundry inmate regret elder mixture tenant taught smirk voter process steady artist equip"
                " jury carve acrobat western cylinder gasoline artwork snapshot ancestor object cinema market species platform iris dragon dive medal",
                "academic acid decision shaft acid carbon credit cards rich living humidity peasant source triumph magazine ladle ruin ocean aspect curious round"
                " main evoke deny stadium zero discuss union strike pencil golden silent geology display wrap peanut listen aide learn juice decision plot bike example"
                " obesity ancient square pistol twice sister hour amuse human hobo hospital escape expect wildlife luck",
                "academic acid decision skin academic vanish olympic evoke gesture rumor unfair scroll grasp very steady include smell diploma package guest greatest"
                " firm humidity trial width priest class large photo sniff survive machine usher stick capacity heat improve predator float iris jacket soldier apart"
                " excuse garden cleanup realize permit dough script veteran crazy theater rival secret drink kernel lips pants",
                "academic acid decision snake acid vegan darkness bucket benefit therapy valuable impulse canyon swing distance vampire round losing twin medal treat"
                " amount fiction hush remind faint distance custody device believe campus guest preach mule exhaust regular short phrase column rescue steady float"
                " mixture testify taught fiction usher snake museum detailed agree intend inherit likely typical blimp symbolic prayer course"
            ]
        )
    }
    assert recover( details_bip39.groups['one'][1][:] + details_bip39.groups['fren'][1][:3] ) == bip39seed

    [(eth,btc)] = details_bip39.accounts
    assert eth.address == "0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E"
    assert btc.address == "bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2"

    #
    # Now, get the exact same derived accounts, but by passing the BIP-39 Seed Entropy (not the generated Seed!)
    #
    bip39entropy		= recover_bip39( 'zoo ' * 11 + 'wrong', as_entropy=True )
    assert codecs.encode( bip39entropy, 'hex_codec' ).decode( 'ascii' ) \
        == 'ff' * 16
    details_bip39entropy	= create(
        "bip39 recovery test", 2, dict( one = (1,1), two = (1,1), fam = (2,4), fren = (3,5) ),
        master_secret=bip39entropy,
        using_bip39=True,
    )
    assert recover( details_bip39entropy.groups['one'][1][:] + details_bip39entropy.groups['fren'][1][:3] ) == bip39entropy

    [(eth,btc)] = details_bip39entropy.accounts
    assert eth.address == "0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E"
    assert btc.address == "bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2"

    #
    # Finally, test that the basic SLIP-39 encoding and derivation using the raw Seed Entropy is
    # different, and yields the expected well-known accounts.
    #
    details_slip39		= create(
        "bip39 recovery test -- all ones in SLIP-39", 2, groups_example, SEED_ONES,
    )
    #print( json.dumps( details_slip39.groups, indent=4 ))
    assert details_slip39.groups == {
        "one": (
            1,
            [
                "academic acid acrobat romp change injury painting safari drug browser trash fridge busy finger standard angry similar overall prune ladybug"
            ]
        ),
        "two": (
            1,
            [
                "academic acid beard romp believe impulse species holiday demand building earth warn lunar olympic clothes piece campus alpha short endless"
            ]
        ),
        "fam": (
            2,
            [
                "academic acid ceramic roster desire unwrap depend silent mountain agency fused primary clinic alpha database liberty silver advance replace medical",
                "academic acid ceramic scared column screw hawk dining invasion bumpy identify anxiety august sunlight intimate satoshi hobo traveler carbon class",
                "academic acid ceramic shadow believe revenue type class station domestic already fact desktop penalty omit actress rumor beaver forecast group",
                "academic acid ceramic sister actress mortgage random talent device clogs craft volume cargo item scramble easy grumpy wildlife wrist simple"
            ]
        ),
        "fren": (
            3,
            [
                "academic acid decision round academic academic academic academic academic academic academic academic academic academic academic academic academic ranked flame amount",
                "academic acid decision scatter biology trial escape element unfair cage wavy afraid provide blind pitch ultimate hybrid gravity formal voting",
                "academic acid decision shaft crunch glance exclude stilt grill numb smug stick obtain raisin force theater duke taught license scramble",
                "academic acid decision skin disaster mama alive nylon mansion listen cowboy suitable crisis pancake velvet aviation exhaust decent medal dominant",
                "academic acid decision snake aunt frozen flip crystal crystal observe equip maximum maiden dragon wine crazy nervous crystal profile fiction"
            ]
        )
    }

    # These are the well-known SLIP-39 0xffff...ffff Seed accounts
    [(eth,btc)] = details_slip39.accounts
    assert eth.address == "0x824b174803e688dE39aF5B3D7Cd39bE6515A19a1"
    assert btc.address == "bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl"

    # And ensure that the SLIP-39 encoding of the BIP-39 "zoo zoo ... wrong" w/ BIP-39
    # Entropy was identically to the raw SLIP-39 encoding.
    assert details_slip39.groups == details_bip39entropy.groups


def into_boolean( val, truthy=(), falsey=() ):
    """Check if the provided numeric or str val content is truthy or falsey; additional tuples of
    truthy/falsey lowercase values may be provided.  The empty/whitespace string is Falsey."""
    if isinstance( val, (int,float,bool)):
        return bool( val )
    assert isinstance( val, str )
    if val.strip().lower() in ( 't', 'true', 'y', 'yes' ) + truthy:
        return True
    elif val.strip().lower() in ( 'f', 'false', 'n', 'no', '' ) + falsey:
        return False
    raise ValueError( val )


def test_recover_bip39_vectors():
    # Test some BIP-39 encodings that have caused issues for other platforms:
    #
    #   - https://github.com/iancoleman/bip39/issues/58

    # If passphrase is None, signals BIP-39 recover as_entropy, and account generation using_bip39
    # bip39_tests		= [
    #     ['zoo ' * 11 + 'wrong', "", True, (
    #         None, 'bech32', 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2')],
    #     ['zoo ' * 11 + 'wrong', "", None, (
    #         None, 'bech32', 'bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl')],
    #     [ 'fruit wave dwarf banana earth journey tattoo true farm silk olive fence', 'banana', True, (
    #         None, 'legacy', '17rxURoF96VhmkcEGCj5LNQkmN9HVhWb7F')]
    # ]
    with open( os.path.join( os.path.splitext( __file__ )[0] + '.csv' )) as bip32_csv:
        bip39_tests		= list( csv.DictReader( bip32_csv, quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL, skipinitialspace=True ))

    for i,t in enumerate( bip39_tests ):
        log.info( f"Testing: {t!r}" )
        # Decode the entropy; either hex or BIP-39 mnemonics support
        entropy			= t.get( 'entropy' )
        if all( c in '0123456789abcdef' for c in entropy.lower() ):
            master_secret	= codecs.decode( entropy, 'hex_codec' )  # Hex entropy allowed
        else:
            passphrase		= ( t.get( 'passphrase', '' )).strip()
            if into_boolean( t.get( 'using_bip39', False )):
                # When using BIP-39, we obtain the 512-bit seed from the 128/256-bit BIP-39 mnemonic
                # entropy + passphrase, and use that to derive the wallets.
                master_secret	= recover_bip39( entropy, passphrase=passphrase )
            else:
                # For SLIP-39 wallets, we recover the 128/256-bit entropy, which is used directly as the
                # seed to derive the wallets.  The passphrase would be used to secure the SLIP-39
                # mnemonics.
                assert not passphrase, \
                    "row {i+1}: passphrase unsupported unless using_bip39"
                master_secret	= recover_bip39( entropy, passphrase=None, as_entropy=True )

        master_secret_hex	= codecs.encode( master_secret, 'hex_codec' ).decode( 'ascii' )
        log.debug( f"Entropy {entropy!r} ==> {master_secret_hex!r}" )

        # Decode the desired address; 1... and xpub... are legacy, 3... and ypub... are segwit and
        # bc1... and zpub are bech32.
        address			= t.get( 'address' )
        format			= {
            '1': 'legacy',
            'x': 'legacy',
            '3': 'segwit',
            'y': 'segwit',
            'b': 'bech32',
            'z': 'bech32',
        }[address[0]]
        acct			= account(
            master_secret	= master_secret,
            crypto		= "BTC",
            path		= t.get( 'path' ),
            format		= format
        )
        # Finally, generate the account's address and xpubkey, and see that one of them match the
        # address in the test case.  Only the address/xpubkey is in the test cases, but lets get the
        # compressed public key as well for comparision w/ the xpubkey derived account...
        addresses		= [ acct.address, acct.pubkey, acct.xpubkey ]
        assert address in addresses, \
            f"row {i+1}: BTC account {address} not in {addresses!r} for entropy {entropy} ==> {master_secret}"
        log.info( f"HD wallet path {acct.path:36}: {commas( addresses )}" )

        # OK, we recovered the same address/xpubkey as the test case did.  Now, if the path ends in
        # at least one layer of non-hardened path, we should be able to:
        #
        #     - remove one (or more) path segments, back to a hardened path component
        #     - generate the xpubkey for the same master_secret, but at that hardened path
        #     - recover a new account using that xpubkey
        #     - generate the same sub-account from it, using the remainder of the path.
        #     - confirm that the address generated by both the original (at full path) and the new
        #       account (from its xpubkey at hardened path + the remaining path) are identical (xpub
        #       will be different, but will produce the same address
        log.info( f"Testing recovery from xpub, generating sub-addresses for {acct.path}" )
        hard,soft		= path_hardened( acct.path )
        log.debug( f"BIP-44 HD path hard: {hard:14}, soft: {soft:8}" )

        acct_hard		= account(
            master_secret	= master_secret,
            crypto		= "BTC",
            path		= hard,
            format		= format
        )
        xpubkey			= acct_hard.xpubkey

        # Now recover from that xpubkey, and use the soft remainder of the path; deduces the addresses format
        acct_xpub		= account(
            master_secret	= xpubkey,
            crypto		= 'BTC',
            path		= soft,
            format		= format,
        )

        # Finally, generate the xpub-derived account's address or xpubkey, and see that one of them
        # match the address in the test case.  NOTE: the xpubkey will differ, but the address will
        # match.  This is because in the presence of the full secret key, both the public and the
        # private SECP256k1 curve points are maintained as the HD wallet path is parsed; when only
        # the public key is available, only it is modified; the secret key information is
        # unavailable, and therefore not modified as each path component is parsed.
        addresses_xpub		= [ acct_xpub.address, acct_xpub.pubkey, acct_xpub.xpubkey ]
        log.info( f"BIP-44 HD path hard: {hard:14}, soft: {soft:8}: {commas( addresses_xpub )}" )

        assert acct_xpub.address in addresses, \
            f"row {i+1}: BTC account {acct_xpub.address} not in original account's {addresses!r} for xpub-derived account"


def test_util():
    assert commas( range(10) ) == '0-9'
    assert commas( [1,2,3,5,6,7] ) == '1-3, 5-7'
    assert commas( [1,2,3,5,6,7], final='and' ) == '1-3 and 5-7'
    assert commas( [1,2,3,5,6,7,9] ) == '1-3, 5-7, 9'
    assert commas( [1,2,3,5,6,7,9], final='and' ) == '1-3, 5-7 and 9'
    assert commas( [1,3,5], final='and' ) == '1, 3 and 5'
    assert commas( [1,2,5], final='or' ) == '1, 2 or 5'

    assert round_onto( -.1, [-5, -1, 0, 1, 5], keep_sign=False ) == 0
    assert round_onto( -.9, [-5, -1, 0, 1, 5], keep_sign=False ) == -1
    assert round_onto( -10, [0, -1, -5, 5, 1], keep_sign=False ) == -5
    assert round_onto( 100, [-5, -1, 0, 1, 5], keep_sign=False ) == +5
    assert round_onto( 100, [0, -1, -5, 5, 1], keep_sign=False ) == +5
    assert round_onto( 2.9, [-5, -1, 0, 1, 5], keep_sign=False ) == +1
    assert round_onto( 3.1, [-5, -1, 0, 1, 5], keep_sign=False ) == +5
    assert round_onto( .01, [-5, -1, 0, 1, 5], keep_sign=False ) == 0
    assert round_onto( -.1, [-5, -1, 0, 1, 5], keep_sign=False ) == 0
    assert round_onto( -.1, [-5, -1, 0, 1, 5], keep_sign=True  ) == -1
    assert round_onto( -.1, [-5, -1,    1, 5], keep_sign=True  ) == -1
    assert round_onto( -.1, [-5,        1, 5], keep_sign=True  ) == -5
    assert round_onto( +.1, [-5, -1,    1, 5], keep_sign=True  ) == +1
    assert round_onto( +.1, [-5, -1,       5], keep_sign=True  ) == +5
    assert round_onto( None, [-5, -1, None, 5], keep_sign=True  ) is None


def test_dft_smoke():
    """Test some basic assumptions on DFTs"""
    print()
    print( "Real-valued samples, recovered from inverse DFT:" )
    x				= [ 2, 3, 5, 7, 11 ]
    print( "vals:  " + ' '.join( f"{f:11.2f}" for f in x ))
    y				= fft( x )
    print( "dft:   " + ' '.join( f"{f:11.2f}" for f in y ))
    z				= ifft( y )
    print( "idft:  " + ' '.join( f"{f:11.2f}" for f in z ))
    zz				= ifft( y )
    assert z == zz  # ensure any memoizing of DFT factors works
    print( "recov.:" + ' '.join( f"{f.real:11.2f}" for f in z ))

    # Ensure a DFT on a power-of-2 length sequence is the same as the pure FFT
    assert dft( x[:4] ) == pytest.approx( pfft( x[:4] ))

    # Lets determine how dft organizes its output buckets.  Lets find the bucket contain any DC
    # offset, by supplying a 0Hz signal w/ a large DC offset.

    # What about a single full real-valued waveform (complex component is always 0j)?
    print()
    print( "Real-valued signal, 1-4 cycles in 8 samples:" )
    dc				= [1.0] * 8
    print( "DC:     " + ' '.join( f"{f:11.2f}" for f in dc ))
    dft_dc			= fft( dc )
    print( "  DFT:  " + ' '.join( f"{f:11.2f}" for f in dft_dc ))
    print( "  DFT_r:" + ' '.join( f"{f:11.2f}" for f in dft_on_real( dft_dc )))
    assert dft_dc[0] == pytest.approx( 8+0j )
    #1Hz:           1.000          0.707          0.000         -0.707         -1.000         -0.707         -0.000          0.707
    #1Hz_d: -0.000+0.000j   4.000-0.000j  -0.000-0.000j   0.000-0.000j   0.000-0.000j   0.000-0.000j   0.000-0.000j   4.000+0.000j
    oneHz			= [math.sin(+math.pi/2+math.pi*2*i/8) for i in range( 8 )]
    print( "+1Hz:   " + ' '.join( f"{f:11.2f}" for f in oneHz ))
    dft_oneHz			= fft( oneHz )
    print( "  DFT:  " + ' '.join( f"{f:11.2f}" for f in dft_oneHz ))
    mags_oneHz			= dft_on_real( dft_oneHz )
    print( "  DFT_r:" + ' '.join( f"{f:11.2f}" for f in mags_oneHz ))
    #2Hz:           1.000          0.000         -1.000         -0.000          1.000          0.000         -1.000         -0.000
    #2Hz_d: -0.000+0.000j  -0.000-0.000j   4.000-0.000j  -0.000-0.000j   0.000-0.000j   0.000-0.000j   4.000+0.000j   0.000-0.000j
    twoHz			= [math.sin(+math.pi/2+math.pi*2*i/4) for i in range( 8 )]
    print( "+2Hz:   " + ' '.join( f"{f:11.2f}" for f in twoHz ))
    dft_twoHz			= fft( twoHz )
    print( "  DFT:  " + ' '.join( f"{f:11.2f}" for f in dft_twoHz ))
    print( "  DFT_r:" + ' '.join( f"{f:11.2f}" for f in dft_on_real( dft_twoHz )))
    #4Hz:           1.000         -1.000          1.000         -1.000          1.000         -1.000          1.000         -1.000
    #4Hz_d:  0.000+0.000j   0.000-0.000j   0.000-0.000j   0.000-0.000j   8.000+0.000j  -0.000+0.000j   0.000-0.000j  -0.000-0.000j
    forHz			= [math.sin(+math.pi/2+math.pi*2*i/2) for i in range( 8 )]
    print( "+4Hz:   " + ' '.join( f"{f:11.2f}" for f in forHz ))
    dft_forHz			= fft( forHz )
    print( "  DFT:  " + ' '.join( f"{f:11.2f}" for f in dft_forHz ))
    print( "  DFT_r:" + ' '.join( f"{f:11.2f}" for f in dft_on_real( dft_forHz )))
    # Same, but just shifted -PI/2, instead of +PI/2: reverses the highest frequency bucket.
    #4Hz:          -1.000          1.000         -1.000          1.000         -1.000          1.000         -1.000          1.000
    #4Hz_d:  0.000+0.000j   0.000+0.000j  -0.000+0.000j  -0.000+0.000j  -8.000-0.000j   0.000-0.000j  -0.000+0.000j   0.000+0.000j
    forHz			= [math.sin(-math.pi/2-math.pi*2*i/2) for i in range( 8 )]
    print( "-4Hz:   " + ' '.join( f"{f:11.2f}" for f in forHz ))
    dft_forHz			= fft( forHz )
    print( "  DFT:  " + ' '.join( f"{f:11.2f}" for f in dft_forHz ))
    print( "  DFT_r:" + ' '.join( f"{f:11.2f}" for f in dft_on_real( dft_forHz )))

    # The rms(sig[:N]) energy in a signal can be obtained either from the original signal, or the rms(FFT)/sqrt(N)
    assert avg( mags_oneHz ) == pytest.approx( 0.533, abs=1e-3 )
    assert rms( oneHz ) == pytest.approx( 0.707, abs=1e-3 )
    assert rms( dft_oneHz ) / math.sqrt( len( dft_oneHz )) == pytest.approx( 0.707, abs=1e-3 )

    # So, the frequency buckets are symmetrical, from DC, 1B/N up to (N/2)B/N (which is also
    # -(N/2)B/N), and then back down to -1B/N.  We do complex signals, so we can see signals of the
    # same frequency on +'ve and -'ve side of DC.  Note that -4/8 and +4/8 are indistinguishable --
    # both rotate the complex signal by 1/2 on each steop, so the "direction" of rotation in complex
    # space is not known.  This is why the signal must be filtered; any frequency components at or
    # above B/2 will simply be mis-interpreted as artifacts in other lower frequency buckets.
    N				= 8
    print()
    print( f"Complex signal, 1-4 cycles in {N} samples:" )
    for rot_i,rot in enumerate((0, 1, 2, 3, -4, -3, -2, -1)):  # buckets, in ascending index order
        sig			= [
            # unit-magnitude complex samples, rotated through 2Pi 'rot' times, in N steps
            cmath.rect(
                1, math.pi*2*rot/N*i
            )
            for i in range( N )
        ]
        print( f"{rot:2} cyc.:" + ' '.join( f"{f:11.2f}" for f in sig ))
        dft_sig			= fft( sig )
        print( "  DFT:  " + ' '.join( f"{f:11.2f}" for f in dft_sig ))
        print( "   ABS: " + ' '.join( f"{abs(f):11.2f}" for f in dft_sig ))
        assert dft_sig[rot_i] == pytest.approx( 8+0j )


SEED_HIGH			= bytes([
    255,      1,
])
SEED_MID			= bytes([
    255,    128,      1,    128,
])
SEED_LOW			= bytes([
    255, 128+90,    128, 128-90,   1, 128-90,    128, 128+90,
])
SEED_SLOW			= bytes([
    255, 128+117, 128+90,  128+49,    128, 128-49,  128-90,  128-117,   1, 128-117, 128-90,  128-49,  128, 128+49, 128+90, 128+117
])


def test_signal_draw():
    # Detect a signal, and draw it at different rates.  First, we need to discover how to "in-fill"
    # a DFT so that the recovered signal is produced at a higher sample rate.  This allows us to
    # analyze a signal in 8-bit values, but produce a recovered signal over 2x 4-bit hex nibbles, or
    # 8x 1-bit bits.
    assert ''.join( signal_draw( s )           for s in range( -128, 128 )) \
        == ',,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,.....................................____________________________________~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'""""""""""""""""""""""""""""""""""""'
    assert ''.join( signal_draw( s, pos=True ) for s in range( -128, 128 )) \
        == '                                                                                                                                ,,,,,,,,,,,,,,,,,,,..................__________________~~~~~~~~~~~~~~~~~~~‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'""""""""""""""""""'
    assert ''.join( signal_draw( s, neg=True ) for s in range( -128, 128 )) \
        == ',,,,,,,,,,,,,,,,,,..................__________________~~~~~~~~~~~~~~~~~~~‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'\'"""""""""""""""""""                                                                                                                                '

    for entropy in (
            SEED_HIGH,     SEED_MID,     SEED_LOW,
            SEED_HIGH * 2, SEED_MID * 2, SEED_LOW * 2,
            SEED_HIGH * 3, SEED_MID * 3, SEED_LOW * 3,
            SEED_HIGH * 4, SEED_MID * 4, SEED_LOW * 4,
    ):
        print()
        print( f"Signal into DFT for {len( entropy )} bytes entropy:" )
        entropy_hex		= codecs.encode( entropy, 'hex_codec' ).decode( 'ascii' )
        entropy_bin		= ''.join( f"{int(h,16):0>4b}" for h in entropy_hex )
        symbols			= len( entropy )
        stride			= 8
        offset			= 0
        dfts			= entropy_bin_dfts( entropy_bin, offset, symbols, stride )

        print( f"Signal from DFT w/  {len( dfts )} bins:" )
        sigR			= signal_recover_real( dfts, integer=True )
        print( f"{entropy_bin}" )
        print( ''.join( stride * signal_draw( s ) for s in sigR ))

        print( "Signal from DFT x 2 deduced (for hex output):" )
        sigR2			= signal_recover_real( dfts, scale=2, integer=True )
        print( f"{entropy_hex}" )
        print( ''.join( signal_draw( s ) * 2 for s in sigR ) + " (low-frequency, expanded x2)" )
        print( ''.join( signal_draw( s ) for s in sigR2 ) + " (scaled x2)" )
        print( ''.join( signal_draw( s, neg=False ) for s in sigR2 ))
        print( ''.join( signal_draw( s, neg=True ) for s in sigR2 ))

        print( "Signal from DFT x 8 deduced (for bin output):" )
        sigR8			= signal_recover_real( dfts, scale=8, integer=True )
        print( f"{entropy_bin}" )
        sigRx8_1		= ''.join( signal_draw( s ) * 8 for s in sigR ) + " (low-frequency, expanded x8)"
        print( sigRx8_1 )
        sigR8_1			= ''.join( signal_draw( s ) for s in sigR8 ) + " (scaled x8)"
        print( sigR8_1 )
        sigR8_pos		= ''.join( signal_draw( s, neg=False ) for s in sigR8 )
        print( sigR8_pos )
        sigR8_neg		= ''.join( signal_draw( s, neg=True ) for s in sigR8 )
        print( sigR8_neg )

    # Validate the very last set of renderings
    assert sigRx8_1 \
        == '""""""""\'\'\'\'\'\'\'\'~~~~~~~~........,,,,,,,,........~~~~~~~~\'\'\'\'\'\'\'\'""""""""\'\'\'\'\'\'\'\'~~~~~~~~........,,,,,,,,........~~~~~~~~\'\'\'\'\'\'\'\'""""""""\'\'\'\'\'\'\'\'~~~~~~~~........,,,,,,,,........~~~~~~~~\'\'\'\'\'\'\'\'""""""""\'\'\'\'\'\'\'\'~~~~~~~~........,,,,,,,,........~~~~~~~~\'\'\'\'\'\'\'\' (low-frequency, expanded x8)'
    assert sigR8_1 \
        == '""""""""\'\'\'\'‾‾‾~~~___....,,,,,,,,,,,,,,,....___~~~‾‾‾\'\'\'\'"""""""""""""""\'\'\'\'‾‾‾~~~___....,,,,,,,,,,,,,,,....___~~~‾‾‾\'\'\'\'"""""""""""""""\'\'\'\'‾‾‾~~~___....,,,,,,,,,,,,,,,....___~~~‾‾‾\'\'\'\'"""""""""""""""\'\'\'\'‾‾‾~~~___....,,,,,,,,,,,,,,,....___~~~‾‾‾\'\'\'\'""""""" (scaled x8)'
    assert f"{sigR8_pos}\n{sigR8_neg}" \
        == '''\
""""""''‾‾~~__.,,                               ,,.__~~‾‾''"""""""""""''‾‾~~__.,,                               ,,.__~~‾‾''"""""""""""''‾‾~~__.,,                               ,,.__~~‾‾''"""""""""""''‾‾~~__.,,                               ,,.__~~‾‾''"""""
                 "''‾~~__..,,,,,,,,,,,..__~~‾''"                                 "''‾~~__..,,,,,,,,,,,..__~~‾''"                                 "''‾~~__..,,,,,,,,,,,..__~~‾''"                                 "''‾~~__..,,,,,,,,,,,..__~~‾''"                \
'''


def test_denoise_mags():
    """See how high we can bring up the noise level before we can no longer detect the signal. """
    print()
    symbols			= 32
    stride			= 8
    threshold			= 200/100

    # Test thru some percentage signal to noise; too high, and we'll overflow our symbols
    noise_pct			= 35

    snr_dB_strides		= {}
    for npct in range( noise_pct ):
        print()
        print( f"For {npct:2d}% noise:" )
        seed_noisy		= [ 128 + noise( 128 * npct/100 ) for _ in range( symbols ) ]  # median 1% noise floor
        for i in range( len( seed_noisy )):
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 16) ) * 16   # max frequency bin
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 14) ) * 14
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 12) ) * 12
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 10) ) * 10
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 8) ) * 8
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 6) ) * 6
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 5) ) * 5
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 4) ) * 4
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 3) ) * 3
            seed_noisy[i]      += math.cos( math.pi * 2 * i / (32 / 2) ) * 2

        SEED_NOISY		= bytes( map( int, map( round, seed_noisy )))
        entropy_hex		= codecs.encode( SEED_NOISY, 'hex_codec' ).decode( 'ascii' )
        entropy_bin		= ''.join( f"{int(h,16):0>4b}" for h in entropy_hex )

        dfts			= entropy_bin_dfts( entropy_bin, 0, symbols=symbols, stride=stride, cancel_dc=True )
        dc			= dfts[0]
        print( "dfts: " + ' '.join( f"{d:{stride*2}.1f}" for d in dfts ))
        nrms, mags		= dft_to_rms_mags( dfts )
        print( f"mags: {' '.join( f'{m:{stride*2}.1f}' for m in mags )}: {sum(mags):7.2f} sum, {avg(mags):7.2f} avg, {nrms:7.2f} RMS; dc: {dc:11.1f} == {abs(dc):7.2f} abs" )
        target, snrs		= denoise_mags( mags, 200/100 )
        snrd			= dict( snrs )  # i: snr
        print( f"snrs: {' '.join( f'{snrd[i]:{stride*2}.1f}' if i in snrd else (' ' * stride*2) for i in range( len( mags )))}: {target=:7.1f}" )
        signal			= signal_entropy( SEED_NOISY, stride=stride, symbols=symbols, threshold=threshold )
        print( f"{signal}" )

        snr_dB_strides[npct]	= (signal.dB, signal.stride)

    for npct,(dB,stride) in snr_dB_strides.items():
        print( f"{npct:02d}%: {stride:2d} bits/symbol, at {dB:7.2f}dB" )

    # We should find the signal at all these noise levels
    assert all( dBS[1] == 8 for dBS in snr_dB_strides.values() )


def test_signal_entropy():
    # See if we can detect patterns of bits in various frequency bins.  With 8x 8-bit real-valued
    # samples, we get DC + 4 frequency bins, with the highest frequency bin representing changes in
    # samples at the peak Nyquist rate; every 2 symbols.  The lowest
    #
    #               256
    #       128+90      128+90
    #   128                      128
    #                                128-90      128+90
    #                                         0
    #
    # We can estimate what perfect noise looks like across all energy bins, and compare our signal
    # against that baseline.  So, our signal has some noise added to it.
    print()
    SEED_SINE			= bytes([
        # 255,    255,    255,    255,
        # 255,    255,    255,    255,
        # 128,    128,    128,    128,
        # 128,    128,    128,    128,
        #   0,      0,      0,      0,
        #   0,      0,      0,      0,
        129,      127,    128,    126,  # 0
        128+20,   128, 128-21,    128,  # 32
        128+21,   128, 128-19,    128,  # 64
        131,      129,    126,    127,  # 96
        127,      129,    126,    129,  # 128
        128+90,   255, 128+90,    128,  # 160
        128-90,     0, 128-90,    128,  # 192
        127,      130,    128,    129,  # 224
    ])

    # Find the highest amplitude signal over 8-symbol chunks; should be the later, lower-frequency
    signal			= signal_entropy( SEED_SINE[:16],  8, 8, threshold=300/100 )
    print( f"{signal}" )
    signal			= signal_entropy( SEED_SINE[-16:], 8, 8, threshold=300/100 )
    print( f"{signal}" )
    signal			= signal_entropy( SEED_SINE,       8, 8, threshold=300/100 )
    print( f"{signal}" )
    assert signal.offset == 160
    assert signal.dB == pytest.approx( 8.7, abs=1e-1 )

    SEED_FF00			= codecs.decode( '7f81' + 'ff00' * 7, 'hex_codec' )
    signal			= signal_entropy( SEED_FF00, 8, 8, threshold=300/100 )
    print( f"SEED_FF00: {signal}" )
    assert signal.offset == 16
    assert signal.dB == pytest.approx( 8.7, abs=1e-1 )
    signal			= signal_entropy( SEED_FF00, 4, 16, threshold=300/100 )
    print( f"SEED_FF00: {signal}" )
    assert signal.offset == 16
    assert signal.dB == pytest.approx( 17.5, abs=1e-1 )

    SEED_F0F0			= codecs.decode( '7f818081' + 'f0f0' * 6, 'hex_codec' )
    signal			= signal_entropy( SEED_F0F0, 8, 8, threshold=300/100 )
    print( f"SEED_F0F0: {signal}" )
    assert signal.offset == 32
    assert signal.dB == pytest.approx( 8.9, abs=1e-1 )
    signal			= signal_entropy( SEED_F0F0, 4, 16, threshold=300/100 )
    print( f"SEED_F0F0: {signal}" )
    assert signal.offset == 32
    assert signal.dB == pytest.approx( 17.0, abs=1e-1 )

    SEED_RAMP			= codecs.decode( '000102030405060708090A0B0C0D0E0F', 'hex_codec' )
    signal			= signal_entropy( SEED_RAMP, 8, threshold=300/100 )
    print( f"SEED_RAMP: {signal}" )
    assert signal.dB == pytest.approx( 15.6, abs=1e-1 )
    signal			= signal_entropy( SEED_RAMP, 4, threshold=250/100 )
    print( f"SEED_RAMP: {signal}" )
    assert "DC offset and every 2 symbols" in signal.details
    assert signal.dB == pytest.approx( 3.7, abs=1e-1 )

    signal			= signal_entropy( SEED_XMAS, threshold=300/100 )
    print( f"SEED_XMAS: {signal}" )
    assert signal.dB == pytest.approx( -2.2, abs=1e-1 )

    signal			= signal_entropy( SEED_XMAS, threshold=300/100, overlap=True )
    print( f"SEED_XMAS: {signal}" )
    assert signal.dB == pytest.approx( -1.5, abs=1e-1 )

    analysis			= analyze_entropy( SEED_XMAS )
    print( f"SEED_XMAS: {analysis}" )
    assert analysis is None


def test_signal_lots():
    # Test that lots of weaker signals still above the threshold are included in the detected
    # Signal.dB ratio.  First, weaker signals just below the threshold, and a couple above.
    # Also confirm that we're normalizing the real-valued magnitudes correctly.
    print()
    seed_lots			= [ 128 + noise( 128 * 1/100 ) for _ in range( 32 ) ]  # median 1% noise floor
    for i in range( len( seed_lots )):
        seed_lots[i]	       += math.cos( math.pi * 2 * i / 2 ) * 16   # max frequency bin
        seed_lots[i]	       += math.cos( math.pi * 2 * i / 8 ) * 4
        seed_lots[i]	       += math.cos( math.pi * 2 * i / (10+2/3) ) * 16  # 32/3 -- exactly the 3rd harmonic
        seed_lots[i]	       += math.cos( math.pi * 2 * i / 32 ) * 16   # low frequency bin

    SEED_LOTS			= bytes( map( int, map( round, seed_lots )))
    stride			= 8
    # Make sure we're computing the complex DFTs to real bins correctly; the same energy in the DC /
    # highest frequency bin (single), and the energy split between +'ve/-'ve frequency complex bins
    # summed into one real magnitude bin, should yield the same magnitudes.
    dfts			= fft( seed_lots )  # DC offset not canceled
    print( f"dfts: {' '.join( f'{b:{stride*2}.1f}' for b in dfts )}" )
    dc				= dfts[0]
    mags			= dft_on_real( dfts )
    print( f"mags: {' '.join( f'{m:{stride*2}.1f}' for m in mags )}: {sum(mags):7.2f} sum, {avg(mags):7.2f} avg, dc: {dc:11.1f} == {abs(dc):7.2f} abs" )
    assert mags[1] == pytest.approx( mags[-1], rel=10/100 )

    signal			= signal_entropy( SEED_LOTS, stride, threshold=300/100, harmonics_max=None )
    print( f"SEED_LOTS: {signal}" )
    assert signal.dB == pytest.approx( +14.8, rel=20/100 )
    # assert "every 32, 10+2/3 and 2 symbols" in signal.details  # order is non-deterministic

    # Now add a strong signal exactly between 2 bins.  The energy of all three signals above
    # threshold should accrue to the result'st SNR dB.  The one that is split across 2 bins should
    # sum to about the same energy as the one concentrated in one bin.
    seed_midl			= [128.] * 32
    midl			= 32/9.5                # harmonics at every 3+5/9 and 3+1/5 symbols
    othr			= 32/5			# and every 6+2/5 symbols
    for i in range( len( seed_lots )):
        seed_midl[i]	       += math.cos( math.pi * 2 * i / midl ) * 60
        seed_midl[i]	       += math.cos( math.pi * 2 * i / othr ) * 40

    SEED_MIDL			= bytes( map( int, map( round, seed_midl )))
    signal			= signal_entropy( SEED_MIDL, stride, threshold=300/100, harmonics_max=None )
    print( f"SEED_MIDL: {signal}" )
    assert signal.dB == pytest.approx( +4.1, abs=1e-1 )
    assert "every 6+2/5, 3+5/9 and 3+1/5 symbols" in signal.details


def test_shannon_entropy():
    shannon			= shannon_entropy( SEED_ONES )
    shannon			= shannon_entropy( SEED_ONES, overlap=False )
    shannon			= shannon_entropy( SEED_ONES, stride=4 )
    shannon			= shannon_entropy( SEED_ONES, stride=4, overlap=False )

    shannon			= shannon_entropy( SEED_ONES+SEED_ZERO )
    print( f"{shannon}" )
    shannon			= shannon_entropy( SEED_ONES+SEED_ZERO, overlap=False )
    print( f"{shannon}" )
    shannon			= shannon_entropy( SEED_ONES+SEED_ZERO, stride=4 )
    print( f"{shannon}" )
    shannon			= shannon_entropy( SEED_ONES+SEED_ZERO, stride=4, overlap=False )
    print( f"{shannon}" )

    shannon			= shannon_entropy( SEED_ONES+SEED_XMAS )
    print( f"{shannon}" )
    shannon			= shannon_entropy( SEED_ONES+SEED_XMAS, overlap=False )
    print( f"{shannon}" )
    shannon			= shannon_entropy( SEED_ONES+SEED_XMAS, stride=4 )
    print( f"{shannon}" )
    shannon			= shannon_entropy( SEED_ONES+SEED_XMAS, stride=4, overlap=False )
    print( f"{shannon}" )

    shannon			= shannon_entropy( SEED_XMAS )
    shannon			= shannon_entropy( SEED_XMAS, stride=6 )
    shannon			= shannon_entropy( SEED_XMAS, stride=6, overlap=False )
    shannon			= shannon_entropy( SEED_XMAS, stride=4 )
    assert shannon.dB == pytest.approx( -7.95, abs=1e-1 )
    shannon			= shannon_entropy( SEED_XMAS )
    assert shannon.dB == pytest.approx( -40.0, abs=1e-1 )
    # Now, add some duplicates, reducing the entropy, 'til we fail the Shannon entropy test.
    shannon			= shannon_entropy( SEED_XMAS[:-3]+SEED_XMAS[:3] )
    print( f"{shannon}" )
    assert shannon.dB == pytest.approx( -3.4, abs=1e-1 )
    shannon			= shannon_entropy( SEED_XMAS[:-4]+SEED_XMAS[:4] )
    print( f"{shannon}" )
    assert shannon.dB == pytest.approx( -0.93, abs=1e-1 )
    shannon			= shannon_entropy( SEED_XMAS[:-5]+SEED_XMAS[:5] )
    print( f"{shannon}" )
    assert shannon.dB == pytest.approx( +0.98, abs=1e-1 )


def kwargs_shannon_limits( kwargs ):
    return compute_entropy_limits( shannon_entropy, **kwargs )


def kwargs_signal_limits( kwargs ):
    return compute_entropy_limits( signal_entropy, **kwargs )


def compute_entropy_limits( compute_entropy, bits, overlap, stride, threshold, setpoint, cycles, checks, symbols=None ):
    avg_over		= (4096, 8192, 16384)
    rejects		= deque( maxlen=16384 )
    rejected		= setpoint
    try:
        for i in range( cycles ):
            entropy	= os.urandom( bits // 8 )
            threshold  *= 1 + ( rejected - setpoint ) / ( 10**(1+math.log(i+1,10)/6) )  # / (10...1000) as i increases from 0 to 100000
            if symbols is None:
                signal	= compute_entropy( entropy, overlap=overlap, stride=stride,
                                           threshold=threshold, show_details=False )
            else:
                signal	= compute_entropy( entropy, overlap=overlap, stride=stride, symbols=symbols,
                                           threshold=threshold, show_details=False )
            reject	= signal.dB >= 0
            rejects.append( reject )
            rejects_lst	= list( rejects )
            rejected	= sum( avg(rejects_lst[-n:]) for n in avg_over ) / len( avg_over )
            if reject or i % checks == 0:
                ( log.info if i % checks == 0 else log.debug )(
                    f" - {i:6} {threshold=:7.5f}: {100*rejected:7.3f}%; "
                    + ', '.join( f"{100*avg(rejects_lst[-n:]):7.3f}%/{n}" for n in avg_over )
                    + f": {signal}"
                )
    except Exception as exc:
        threshold	= exc
    finally:
        print( f"{compute_entropy.__name__} for {bits}-bit entropy w/ {overlap=:5}, {stride=:3}; {rejected*100:7.3f}% (latest avg), {avg(rejects)*100:7.3f}% rejects total: {threshold=}" )
        return (bits, overlap, stride, symbols, threshold)


def test_shannon_limits( detailed=False ):
    """Compute the threshold at which ~99.9% of good random entropy are accepted, at each combination
    of stride.  Only runs full test only at high logging levels.

    """
    shannon_limits		= {}
    strengths			= (128, 256, 512) + (160, 192, 224)  # SLIP-39 + BIP-39
    strides			= (3, 4, 5, 6, 7, 8)
    overlapping			= (False, True)
    cycles			= 150001
    checks			= 10000
    if not detailed:
        strengths		= strengths[-1:]
        strides			= strides[-2:]
        #overlapping		= overlapping[:1]
        cycles			= 1001
        checks			= 100

    threshold			= 10/100
    setpoint			= 0.15/100
    poolkwargs			= []
    for bits in strengths:
        for overlap in overlapping:  # noqa: E111
            for stride in strides:
                poolkwargs.append( dict(
                    bits	= bits,
                    overlap	= overlap,
                    stride	= stride,
                    threshold	= threshold,
                    setpoint	= setpoint,
                    cycles	= cycles,
                    checks	= checks,
                ))
    with multiprocessing.Pool(32) as pool:
        for (bits, overlap, stride, symbols, threshold) in pool.map( kwargs_shannon_limits, poolkwargs ):
            if isinstance( threshold, Exception ):
                print( f"Shannon Limits: Failed for {bits=:3}, {overlap=:5}, {symbols=:3}: {threshold}" )
            else:
                shannon_limits.setdefault(
                    overlap, {} ).setdefault(
                        bits, {} )[stride] = threshold
    print( f"Shannon limits: {json.dumps( shannon_limits, indent=4, default=str, sort_keys=True )}" )


def test_signal_limits( detailed=False ):
    """Compute the threshold at which ~99.9% of good random entropy are accepted, at each combination
    of stride.  Only runs full test only at high logging levels.

    """
    signal_limits		= {}
    strengths			= (128, 256, 512) + (160, 192, 224)  # SLIP-39 + BIP-39
    strides			= (3, 4, 5, 6, 7, 8)
    overlapping			= (False, True)
    cycles			= 150001
    checks			= 10000
    if not detailed:
        strengths		= strengths[:1]
        strides			= strides[:-2]
        #overlapping		= overlapping[:1]
        cycles			= 1001
        checks			= 100

    threshold			= 300/100
    setpoint			= 0.15/100
    poolkwargs			= []
    for bits in strengths:
        for overlap in overlapping:  # noqa: E111
            for stride in strides:
                for symbols in range( bits // stride - 3, bits // stride + 1 ):
                    poolkwargs.append( dict(
                        bits		= bits,
                        overlap		= overlap,
                        symbols		= symbols,
                        stride		= stride,
                        threshold	= threshold,
                        setpoint	= setpoint,
                        cycles		= cycles,
                        checks		= checks,
                    ))
    with multiprocessing.Pool(32) as pool:
        for (bits, overlap, stride, symbols, threshold) in pool.map( kwargs_signal_limits, poolkwargs ):
            if isinstance( threshold, Exception ):
                print( f"Signal Limits: Failed for {bits=:3}, {overlap=:5}, {symbols=:3}: {threshold}" )
            else:
                signal_limits.setdefault(
                    overlap, {} ).setdefault(
                        bits, {} ).setdefault(
                            stride, {} )[symbols] = threshold
    print( f"Signal limits: {json.dumps( signal_limits, indent=4, default=str, sort_keys=True )}" )


def test_poor_entropy():
    """Test various entropy to determine if we see a failure of Shannon entropy or Signals.

    """
    # Some really bad entropy that perfectly match the highest frequency DFT bins in an 16-symbol
    # complex DFT (DC+5 magnitudes real).  Try to determine how to determine the frequency buckets.

    entropy			= SEED_HIGH * 8
    signal			= signal_entropy( entropy, stride=8, symbols=16, threshold=300/100, overlap=False, ignore_dc=True )
    log.info( f"Signal high frequency: {signal}" )
    assert signal.dB == pytest.approx( +19.1, abs=1e-1 )

    entropy			= SEED_MID * 4
    signal			= signal_entropy( entropy, stride=8, symbols=16, overlap=False, ignore_dc=True )
    log.info( f"Signal mid. frequency: {signal}" )
    assert signal.dB == pytest.approx( +14.7, abs=1e-1 )

    entropy			= SEED_LOW * 2
    signal			= signal_entropy( entropy, stride=8, symbols=16, overlap=False, ignore_dc=True )
    log.info( f"Signal low  frequency: {signal}" )
    assert signal.dB == pytest.approx( +14.7, abs=1e-1 )

    entropy			= SEED_SLOW
    signal			= signal_entropy( entropy, stride=8, symbols=16, overlap=False, ignore_dc=True )
    log.info( f"Signal slow  frequency: {signal}" )
    assert signal.dB == pytest.approx( +14.6, abs=1e-1 )

    # Some bad "random" dice rolls.  These are ASCII data, so only 8-bit symbol strides, and ignore
    # DC offset.
    entropy			= "34131214324563463456112412364563".encode( 'ASCII' )
    signal			= signal_entropy( entropy, stride=8, symbols=32, overlap=False, threshold=250/100, ignore_dc=True )
    log.info( f"Signal in bad dice rolls: {signal}" )
    assert signal.dB == pytest.approx( +2.1, abs=1e-1 )
    assert "every 16 symbols" in signal.details

    analysis			= analyze_entropy( entropy, strides=8, overlap=False, ignore_dc=True )
    print( f"Analysis of bad dice rolls: {analysis}" )

    # Some bad "random" entropy in a base-64 phrase; see if we can pick it out
    entropy			= base64.b64decode( "The-quick-brown-fox-jumps-over-the-lazy-dog=", altchars='-_', validate=True )
    signal			= signal_entropy( entropy, stride=6, overlap=False, threshold=200/100, ignore_dc=True )
    log.info( f"Signal in bad base-64 string: {signal}" )
    assert signal.dB == pytest.approx( +0.4, abs=1e-1 )
    assert "every 5+1/4 symbols" in signal.details

    signal			= shannon_entropy( entropy, stride=6, overlap=True, threshold=10/100 )
    log.info( f"Shannon in bad base-64 string: {signal}" )
    assert signal.dB == pytest.approx( +5.9, abs=1e-1 )

    signals, shannons		= scan_entropy( entropy, shannon_threshold=10/100 )
    #assert len( signals ) == 3
    assert len( shannons ) == 3

    analysis			= analyze_entropy( entropy )
    print( f"Analysis of base-64 phrase: {analysis}" )
    assert analysis and "Shannon entropy reduced at offset 5 in 41x 6-bit symbols" in analysis


def test_good_entropy():
    entropy			= SEED_XMAS
    signal			= signal_entropy( entropy )
    log.info( f"Signal XMAS frequency: {signal}" )
    assert signal.dB == pytest.approx( -4.3, abs=1e-1 )

    analysis			= analyze_entropy( entropy )
    print( f"Analysis of XMAS entropy: {analysis}" )
    assert analysis is None

    analysis			= analyze_entropy( entropy[:4]
                                                   + 2 * codecs.decode( "DeadBeef", 'hex_codec' )
                                                   + entropy[12:])
    print( f"Analysis of XMAS entropy w/ 0xDeadBeef: {analysis}" )

    analysis			= analyze_entropy( entropy[:-5] + entropy[:5] )
    print( f"Analysis of XMAS entropy w/ 5 dups: {analysis}" )
    assert analysis and "Shannon entropy reduced" in analysis

    # This test takes a while without numpy installed, due to inefficient python-only dft
    cycles			= 1000
    analysis_bad		= []
    signals_bad			= []
    shannon_bad			= []
    for i in range( cycles ):
        entropy			= secrets.token_bytes( 256 // 8 )
        analysis		= analyze_entropy( entropy )
        if analysis:
            analysis_bad.append( analysis )
            if "Signal" in analysis:
                signals_bad.append( analysis )
                print( f"{ordinal(i)} analysis shows Signal energy: {analysis}" )
            if "Shannon" in analysis:
                shannon_bad.append( analysis )

    print( f"Analyzed {cycles} random entropy and found {100*len(analysis_bad)/cycles:.1f}% bad" )
    print( f"  Signals failure found {100*len(signals_bad)/cycles:.1f}%" )
    print( f"  Shannon failure found {100*len(shannon_bad)/cycles:.1f}%" )
    assert len( analysis_bad ) / cycles < 5/100
    assert len( shannon_bad ) / cycles < 3/100
    assert len( signals_bad ) / cycles < 3/100


def test_rngs_entropy( detailed=False ):
    """Test various RNGs to observe that they exhibit similar spectral features.

    """
    def rng_secrets( n ):
        return secrets.token_bytes( n )

    def rng_os( n ):
        return os.urandom( n )

    def rng_py( n ):
        return rng_py.R.randbytes( n )
    rng_py.R			= random.Random(
        os.urandom( 32 )
    )

    def rng_hash( n ):
        """Introduce n bytes of entropy into the SHA512, and then extract stretched entropy from the low
        half of the digest, re-hashing as necessary.  Basically a poor RNG based on SHA512.

        """
        def hasher():
            while True:
                digest		= rng_hash.H.digest()
                for i in range( 256 ):
                    yield digest[i:i+1]
                rng_hash.H.update( digest )
        rng_hash.H.update( rng_os( n ))
        return b''.join( itertools.islice( hasher(), n ))
    rng_hash.H			= hashlib.sha512()

    def rng_recycle( n ):
        """Every random 10 or so bytes, recycle a byte."""
        def recycler():
            while True:
                b		= rng_os( 2 )
                if b[1] % 10 == 0:
                    yield b[:1]
                yield b[:1]
        return b''.join( itertools.islice( recycler(), n ))

    def eval_rng( rng, count, bits=256 ):
        stat			= dict(
            shannons_dBs= [],
            signals_dBs	= [],
        )
        for i in range( count ):
            entropy		= rng( bits // 8 )
            signals, shannons	= scan_entropy( entropy )
            stat['signals_dBs'].append( signals )
            stat['shannons_dBs'].append( shannons )
        return stat

    summ			= {}
    count			= 1000
    if not detailed:
        count			= 10
    for rng in ( rng_os, rng_secrets, rng_py, rng_hash, rng_recycle ):
        stat			= eval_rng( rng, count )

        summ.setdefault( rng.__name__, {} )['signals pct'] \
            = avg( list( bool( s ) for s in stat['signals_dBs'] ))
        summ.setdefault( rng.__name__, {} )['shannons pct'] \
            = avg( list( bool( s ) for s in stat['shannons_dBs'] ))
        summ.setdefault( rng.__name__, {} )['signals avg'] \
            = avg( list( s[0].dB for s in stat['signals_dBs'] if s ))
        summ.setdefault( rng.__name__, {} )['shannons avg'] \
            = avg( list( s[0].dB for s in stat['shannons_dBs'] if s ))

        for n in 'signals', 'shannons':
            for i,s in enumerate( sorted(
                    (
                        s[0] for s in stat[n + '_dBs']
                        if s
                    ),
                    reverse=True
            )[:3] ):
                print( f"{ordinal(i)} {rng.__name__}: {s}" )

    print( f"Summary (goal is ~1% of entropy reports signals/shannon failure): {json.dumps( summ, indent=4)}" )


if __name__ == "__main__":
    #import cProfile
    #cProfile.run( 'test_signal_limits( detailed=True ); test_shannon_limits( detailed=True )' )
    #cProfile.run( 'test_shannon_limits( detailed=True )' )
    #test_shannon_limits( detailed=True )
    test_signal_limits( detailed=True )
