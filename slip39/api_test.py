import codecs

import pytest
import shamir_mnemonic

from .generate_test	import substitute, nonrandom_bytes
from .generate		import account, create
from .recovery		import recover, recover_bip39

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
def test_bip39():
    bip39seed			= recover_bip39( 'zoo ' * 11 + 'wrong' )
    details			= create(
        "bip39 recovery test", 2, dict( one = (1,1), two = (1,1), fam = (2,4), fren = (3,5) ),
        master_secret=bip39seed,
    )
    #import json
    #print( json.dumps( details.groups, indent=4 ))
    assert details.groups == {
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
    assert recover( details.groups['one'][1][:] + details.groups['fren'][1][:3] ) == bip39seed
