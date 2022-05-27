import codecs
import pytest

import shamir_mnemonic

from .api		import create
from .recovery		import recover, recover_bip39
from .dependency_test	import substitute, nonrandom_bytes, SEED_XMAS, SEED_ONES

groups_example			= dict( one = (1,1), two = (1,1), fam = (2,4), fren = (3,5) )


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
    import json
    print( json.dumps( details_slip39.groups, indent=4 ))
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
