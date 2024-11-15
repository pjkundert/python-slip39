# -*- mode: python ; coding: utf-8 -*-
import json
import pytest

try:
    import eth_account
except ImportError:
    eth_account			= None
try:
    from Crypto.Cipher	import AES
    from Crypto.Protocol.KDF import scrypt
except ImportError:
    AES				= None
    scrypt			= None

import shamir_mnemonic

from .			import account, create, addresses, addressgroups, accountgroups, Account
from .recovery		import recover

from .dependency_test	import substitute, nonrandom_bytes, SEED_XMAS, SEED_ONES

BIP39_ABANDON			= "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
BIP39_ZOO			= 'zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong'


def test_account_smoke():
    acct			= account( SEED_XMAS )
    assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'
    assert acct.path == "m/44'/60'/0'/0/0"
    assert acct.key == '178870009416174c9697777b1d94229504e83f25b1605e7bb132aa5b88da64b6'

    acct			= account( SEED_XMAS, path="m/44'/60'/0'/0/1" )
    assert acct.address == '0x3b774e485fC818F0f377FBA657dfbF92B46f8504'
    assert acct.path == "m/44'/60'/0'/0/1"
    assert acct.pubkey == '03cbcf791b37011feab1c5d797cd76a3fa0f12ee5582adbe5aa4d8172a7bbaba5b'
    assert acct.key == acct.prvkey == 'bf299fe7a7d948fdb98474557bbee73395e01f3a6a73638d45d345f9adb451fb'
    assert acct.xpubkey == 'xpub6FVwqKQUrDre2ZPtAvcqR7GYW4662JTM7R1FGuwGAH3b1TjntLCbMa3HY7C1BR4ifXEtwfX63a69FEAcCSCgrgQZNd3WYgvKhAghRNucEc6'
    assert acct.xprvkey == 'xprvA2WbRosb1rJLp5KR4u5q3yKox2FbcqjVkC5eUXXebwWc8fQeLntLomiogp7vVMZcGfB4vaKeWRJ6eQmHSPRk6W7AJRNx2TT3Ai825JwH9kG'
    # And ensure we can round-trip the xprvkey (the x{pub/prv}keys encode other info, so won't be the same)
    acct			= account( acct.xprvkey, path="m/" )
    assert acct.path == 'm/'
    assert acct.address == '0x3b774e485fC818F0f377FBA657dfbF92B46f8504'
    assert acct.pubkey == '03cbcf791b37011feab1c5d797cd76a3fa0f12ee5582adbe5aa4d8172a7bbaba5b'
    assert acct.key == acct.prvkey == 'bf299fe7a7d948fdb98474557bbee73395e01f3a6a73638d45d345f9adb451fb'

    acct			= account( SEED_XMAS, crypto='Bitcoin' )
    assert acct.address == 'bc1qz6kp20ukkyx8c5t4nwac6g8hsdc5tdkxhektrt'
    assert acct.path == "m/84'/0'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Bitcoin', format='Legacy' )
    assert acct.address == '19FQ983heQEBXmopVNyJKf93XG7pN7sNFa'
    assert acct.path == "m/44'/0'/0'/0/0"
    assert acct.pubkey == '02d0bca9d976ad7303d1c0c3fd6ad0cb6bb78077d2ff158c16ac21bed763fb49a8'

    acct			= account( SEED_XMAS, crypto='Bitcoin', format='SegWit' )
    assert acct.path == "m/49'/0'/0'/0/0"
    assert acct.address == '3KbLyVYmzoDXtXMMemWV2JvvhWuWZzP5Sa'

    # And, confirm that we retrieve the same Bech32 address for the all-ones seed,
    # as on a real Trezor "Model T".
    acct			= account( SEED_ONES, crypto='Bitcoin' )
    assert acct.path == "m/84'/0'/0'/0/0"
    assert acct.address == 'bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl'
    assert acct.pubkey == '038f7fa5776f5359eb861994bee043f0b16a5ca24b66eb38696a7325d3e1717e72'
    assert acct.prvkey == acct.key == '80d5082773a4d2a07ee667a772ca13a120a5fc9d61bcf5a32f9e7ccf731bc0e6'
    assert acct.xpubkey == 'zpub6uMZYEpdewNa98z7Hge3R4GzeayoXCmtPUzFV7DVa4cc36k2Xh7oEDvs6baStXLxT8VtXkBZ56yfuk4D5JvM43nbB7EpdkmJC75ScEZm2QK'
    assert acct.xprvkey == 'zprvAgND8jHjpZpGveueBf733vLG6Z9K7k432G4egiot1j5dAJQsz9oYgRcPFJVUdpLe3tHnabyRmmuGY871GdTv8tkotCwyn6Ec5bZbb8RjtHF'

    acct			= account( SEED_XMAS, crypto='Litecoin' )
    assert acct.address == 'ltc1qfjepkelqd3jx4e73s7p79lls6kqvvmak5pxy97'
    assert acct.path == "m/84'/2'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Litecoin', format='Legacy' )
    assert acct.address == 'LeyK1dbc5qKdKC9TvkygMTeoHixR3z1XG3'
    assert acct.path == "m/44'/2'/0'/0/0"

    acct			= account( SEED_XMAS, crypto='Litecoin', format='SegWit' )
    assert acct.path == "m/49'/2'/0'/0/0"
    assert acct.address == 'MK18ZPy9KR6PiCzti61s3HoNmEEGMmAEKc'

    acct			= account( SEED_XMAS, crypto='Dogecoin' )
    assert acct.address == 'DQCnF49GwQ5auL3u5c2uow62XS57RCA2r1'
    assert acct.path == "m/44'/3'/0'/0/0"

    acct			= account( SEED_ONES, crypto='Ripple' )
    assert acct.path == "m/44'/144'/0'/0/0"  # Default
    assert acct.address == 'rsXwvDVHHPrSm23gogdxJdrJg9WBvqRE9m'

    # Fake up some known Ripple pubkey --> addresses, by replacing the underlying "compressed"
    # public key function to return a fixed value.  Test values from:
    # trezor-firmware/core/tests/test_apps.ripple.address.py
    compressed_save		= acct.hdwallet.compressed
    acct.hdwallet.compressed	= lambda: 'ed9434799226374926eda3b54b1b461b4abf7237962eae18528fea67595397fa32'
    assert acct.pubkey == 'ed9434799226374926eda3b54b1b461b4abf7237962eae18528fea67595397fa32'
    assert acct.address == 'rDTXLQ7ZKZVKz33zJbHjgVShjsBnqMBhmN'
    acct.hdwallet.compressed	= lambda: '03e2b079e9b09ae8916da8f5ee40cbda9578dbe7c820553fe4d5f872eec7b1fdd4'
    assert acct.address == 'rhq549rEtUrJowuxQC2WsHNGLjAjBQdAe8'
    acct.hdwallet.compressed	= lambda: '0282ee731039929e97db6aec242002e9aa62cd62b989136df231f4bb9b8b7c7eb2'
    assert acct.address == 'rKzE5DTyF9G6z7k7j27T2xEas2eMo85kmw'
    acct.hdwallet.compressed	= compressed_save

    # Test values from a Trezor "Model T" w/ root seed 'zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong' loaded.
    # The Trezor Suite UI produced the following account derivation path and public address for:
    acct			= account( BIP39_ZOO, crypto='Ripple' )
    assert acct.path == "m/44'/144'/0'/0/0"  # Default
    assert acct.address == 'rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV'
    assert acct.pubkey == '039d65db4964cbf2049ad49467a6b73e7fec7d6e6f8a303cfbdb99fa21c7a1d2bc'
    assert acct.prvkey == '6501276b9d7f646742feb12fd066e107af8c1e26e4ad7c2694279d44c43bdfb2'


def test_account_format():
    """Bitcoin test vectors from https://github.com/satoshilabs/slips/blob/master/slip-0132.md

    Since these test vectors use only the hardened path eg. m/44'/0'/0', and not the full HD
    derivation path, and since we also want to test the default paths used for various address
    formats, we'll need to use the accountgroups API (the regular account API doesn't include a
    means to restrict the path to hardened_defaults).

    """
    # Legacy Bitcoin
    acct			= account(
        master_secret	= BIP39_ABANDON,
        crypto		= 'Bitcoin',
        format		= "legacy",
    )
    assert acct.format == 'legacy'
    assert acct.hdwallet.seed() == "5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc19a5ac40b389cd370d086206dec8aa6c43daea6690f20ad3d8d48b2d2ce9e38e4"
    assert acct.path == "m/44'/0'/0'/0/0"
    assert acct.address == '1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA'

    # m/44'/0'/0'
    (acct,),			= accountgroups(
        BIP39_ABANDON, cryptopaths=['Bitcoin'], format='legacy', hardened_defaults=True,
    )
    assert acct.format == 'legacy'
    assert acct.path == "m/44'/0'/0'"
    assert acct.xprvkey == "xprv9xpXFhFpqdQK3TmytPBqXtGSwS3DLjojFhTGht8gwAAii8py5X6pxeBnQ6ehJiyJ6nDjWGJfZ95WxByFXVkDxHXrqu53WCRGypk2ttuqncb"
    assert acct.xpubkey == "xpub6BosfCnifzxcFwrSzQiqu2DBVTshkCXacvNsWGYJVVhhawA7d4R5WSWGFNbi8Aw6ZRc1brxMyWMzG3DSSSSoekkudhUd9yLb6qx39T9nMdj"

    # m/44'/0'/0'/0/0
    acct.from_path( "m/0/0" )
    assert acct.path == "m/44'/0'/0'/0/0"
    assert acct.address == "1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA"

    acct			= account( BIP39_ABANDON, crypto="Bitcoin", format='legacy' )
    assert acct.format == 'legacy'
    assert acct.path == "m/44'/0'/0'/0/0"
    assert acct.address == "1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA"

    acct			= account(
        master_secret	= BIP39_ABANDON,
        crypto		= "BTC",
        path		= "...//",
        format		= "legacy",
    )
    assert acct.format == 'legacy'
    assert acct.hdwallet.semantic() == "p2pkh"
    assert acct.path == "m/44'/0'/0'"
    assert acct.xprvkey == "xprv9xpXFhFpqdQK3TmytPBqXtGSwS3DLjojFhTGht8gwAAii8py5X6pxeBnQ6ehJiyJ6nDjWGJfZ95WxByFXVkDxHXrqu53WCRGypk2ttuqncb"
    assert acct.xpubkey == "xpub6BosfCnifzxcFwrSzQiqu2DBVTshkCXacvNsWGYJVVhhawA7d4R5WSWGFNbi8Aw6ZRc1brxMyWMzG3DSSSSoekkudhUd9yLb6qx39T9nMdj"

    # SegWit
    acct			= account(
        master_secret	= BIP39_ABANDON,
        crypto		= "Bitcoin",
        format		= 'segwit'
    )
    assert acct.hdwallet.seed() == "5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc19a5ac40b389cd370d086206dec8aa6c43daea6690f20ad3d8d48b2d2ce9e38e4"
    assert acct.hdwallet.network() == "mainnet"
    assert acct.hdwallet.p2pkh_address() == "1PkaFBUcyAccDp2Xo2K8MqduVMgMB792r2"
    assert acct.hdwallet.p2sh_address() == "3LWUBjP2jcWhippRcyKUX1kkHNakUAy2Ms"
    assert acct.hdwallet.p2wpkh_address() == "bc1qlxgx0xk2lcjuyas4xua5p0ezg3kjfl6yd3h8y6"
    assert acct.hdwallet.p2wpkh_in_p2sh_address() == "37VucYSaXLCAsxYyAPfbSi9eh4iEcbShgf"
    assert acct.hdwallet.p2wsh_in_p2sh_address() == "3Kdr7CoTcx8UaGuzD7aqQxXi1dxUmBdph2"
    assert acct.format == "segwit"
    assert acct.hdwallet.semantic() == "p2wpkh_in_p2sh"
    assert acct.path == "m/49'/0'/0'/0/0"
    assert acct.address == "37VucYSaXLCAsxYyAPfbSi9eh4iEcbShgf"

    (acct,),			= accountgroups(
        BIP39_ABANDON, cryptopaths=['Bitcoin'], format='segwit', hardened_defaults=True,
    )
    assert acct.format == "segwit"
    assert acct.path == "m/49'/0'/0'"
    assert acct.xprvkey == "yprvAHwhK6RbpuS3dgCYHM5jc2ZvEKd7Bi61u9FVhYMpgMSuZS613T1xxQeKTffhrHY79hZ5PsskBjcc6C2V7DrnsMsNaGDaWev3GLRQRgV7hxF"
    assert acct.xpubkey == "ypub6Ww3ibxVfGzLrAH1PNcjyAWenMTbbAosGNB6VvmSEgytSER9azLDWCxoJwW7Ke7icmizBMXrzBx9979FfaHxHcrArf3zbeJJJUZPf663zsP"

    acct.from_path( "m/0/0" )
    assert acct.path == "m/49'/0'/0'/0/0"
    assert acct.address == "37VucYSaXLCAsxYyAPfbSi9eh4iEcbShgf"

    # Bech32
    (acct,),			= accountgroups(
        BIP39_ABANDON, cryptopaths=['Bitcoin'], format='bech32', hardened_defaults=True,
    )
    assert acct.format == "bech32"
    assert acct.hdwallet.semantic() == "p2wpkh"
    assert acct.path == "m/84'/0'/0'"
    assert acct.xprvkey == "zprvAdG4iTXWBoARxkkzNpNh8r6Qag3irQB8PzEMkAFeTRXxHpbF9z4QgEvBRmfvqWvGp42t42nvgGpNgYSJA9iefm1yYNZKEm7z6qUWCroSQnE"
    assert acct.xpubkey == "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs"

    # "m/84'/0'/0'/0/0"
    acct.from_path( "m/0/0" )
    assert acct.path == "m/84'/0'/0'/0/0"
    assert acct.address == "bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu"

    acct			= account(
        master_secret	= BIP39_ABANDON,
        crypto		= "BTC",
        path		= "...//",
        format		= "bech32",
    )
    assert acct.hdwallet.seed() == "5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc19a5ac40b389cd370d086206dec8aa6c43daea6690f20ad3d8d48b2d2ce9e38e4"
    assert acct.format == "bech32"
    assert acct.hdwallet.semantic() == "p2wpkh"
    assert acct.path == "m/84'/0'/0'"
    assert acct.xprvkey == "zprvAdG4iTXWBoARxkkzNpNh8r6Qag3irQB8PzEMkAFeTRXxHpbF9z4QgEvBRmfvqWvGp42t42nvgGpNgYSJA9iefm1yYNZKEm7z6qUWCroSQnE"
    assert acct.xpubkey == "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs"

    acct			= account(
        master_secret	= BIP39_ABANDON,
        crypto		= 'Bitcoin',
        format		= "bech32"
    )
    assert acct.format == "bech32"
    assert acct.hdwallet.seed() == "5eb00bbddcf069084889a8ab9155568165f5c453ccb85e70811aaed6f6da5fc19a5ac40b389cd370d086206dec8aa6c43daea6690f20ad3d8d48b2d2ce9e38e4"
    assert acct.path == "m/84'/0'/0'/0/0"
    assert acct.address == 'bc1qcr8te4kr609gcawutmrza0j4xv80jy8z306fyu'


def test_slip39_non_extendable_compatibility():
    """Test that SLIP-39 non-extendable backup of a wallet generated by Trezor can be recevered"""
    # The 4th vector from https://github.com/trezor/python-shamir-mnemonic/blob/master/vectors.json
    mnemonics = [
        "shadow pistol academic always adequate wildlife fancy gross oasis cylinder mustang wrist rescue view short owner flip making coding armed",
        "shadow pistol academic acid actress prayer class unknown daughter sweater depict flip twice unkind craft early superior advocate guest smoking"
    ]
    account = Account( crypto="Bitcoin", format="legacy" )
    account.from_mnemonic( "\n".join(mnemonics), passphrase = 'TREZOR', path="m/" )
    assert account.xprvkey == "xprv9s21ZrQH143K2nNuAbfWPHBtfiSCS14XQgb3otW4pX655q58EEZeC8zmjEUwucBu9dPnxdpbZLCn57yx45RBkwJHnwHFjZK4XPJ8SyeYjYg"


def test_slip39_extendable_trezor_compatibility():
    """Test that SLIP-39 extendable backup of a wallet generated by Trezor can be recevered"""
    # The 43th vector from https://github.com/trezor/python-shamir-mnemonic/blob/master/vectors.json
    mnemonics = [
        "enemy favorite academic acid cowboy phrase havoc level response walnut budget painting inside trash adjust froth kitchen learn tidy punish",
        "enemy favorite academic always academic sniff script carpet romp kind promise scatter center unfair training emphasis evening belong fake enforce"
    ]
    account = Account( crypto="Bitcoin", format="legacy" )
    account.from_mnemonic( "\n".join(mnemonics), passphrase = 'TREZOR', path="m/" )
    assert account.xprvkey == "xprv9s21ZrQH143K4FS1qQdXYAFVAHiSAnjj21YAKGh2CqUPJ2yQhMmYGT4e5a2tyGLiVsRgTEvajXkxhg92zJ8zmWZas9LguQWz7WZShfJg6RS"


def test_account_from_mnemonic():
    """Test all the ways the entropy 0xffff...ffff can be encoded and HD Wallets derived."""
    # Raw 0xffff...ffff entropy as Seed.  Not BIP-39 decoded (hashed) via mnemonic to produce Seed.
    # This is how SLIP-39 encodes and decodes entropy.  The raw HD Wallet Seed directly uses the
    # entropy, un-molested.
    acct_ones			= account( SEED_ONES, crypto='Bitcoin' )
    assert acct_ones.path == "m/84'/0'/0'/0/0"  # Default, BTC
    assert acct_ones.address == 'bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl'

    details_ones_native_slip39	= create(
        "SLIP39 Wallet: Ones native SLIP-39",
        1,
        dict( fren = (3,5) ),
        SEED_ONES
    )
    # And the account addresses documented in the create's details are the SLIP-39 encodings (Seed
    # uses raw entropy)
    assert len(details_ones_native_slip39.accounts) == 1
    [(eth,btc)] = details_ones_native_slip39.accounts  # The default accounts created are ETH, BTC
    assert btc.address == 'bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl'
    # But, we recover the raw entropy (as always from SLIP-39), except if using_bip39 is specified
    assert recover( details_ones_native_slip39.groups['fren'][1][:3] ) == SEED_ONES
    assert account( '\n'.join( details_ones_native_slip39.groups['fren'][1][:3] ), crypto='BTC' ).address == 'bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl'
    assert account( '\n'.join( details_ones_native_slip39.groups['fren'][1][:3] ), crypto='BTC', using_bip39=True ).address == 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'

    # Now 0xffff...ffff entropy as BIP-39 Seed.
    acct_ones_bip39		= account( BIP39_ZOO, crypto='BTC' )
    assert acct_ones_bip39.address == 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'

    details_ones_using_bip39	= create(
        "SLIP39 Wallet: Ones using BIP-39",
        1,
        dict( fren = (3,5) ),
        SEED_ONES,
        using_bip39 = True,
    )
    # And the account addresses documented are those from the BIP-39 derived Seed
    assert len(details_ones_using_bip39.accounts) == 1
    [(eth,btc)] = details_ones_using_bip39.accounts  # The default accounts created are ETH, BTC
    assert btc.address == 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'
    # But, we recover the raw entropy (as always from SLIP-39), except if using_bip39 is specified
    assert recover( details_ones_using_bip39.groups['fren'][1][:3] ) == SEED_ONES
    assert account( '\n'.join( details_ones_using_bip39.groups['fren'][1][:3] ), crypto='BTC' ).address == 'bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl'
    assert account( '\n'.join( details_ones_using_bip39.groups['fren'][1][:3] ), crypto='BTC', using_bip39=True ).address == 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'

    # Now for Ripple (XRP) accounts; first with native SLIP-39 Seed encoding
    acct			= account( SEED_ONES, crypto='Ripple' )
    assert acct.path == "m/44'/144'/0'/0/0"  # Default, XRP
    assert acct.address == 'rsXwvDVHHPrSm23gogdxJdrJg9WBvqRE9m'
    acct			= account( SEED_ONES, crypto='Ripple', path="../1" )
    assert acct.path == "m/44'/144'/0'/0/1"
    assert acct.address == 'rfMBrTc7VRTLUZu2K517r594Ky9qU5fQ5i'
    # Then with BIP-39 Seed encoding from same 0xffff...ffff entropy.  We'll test using the *same*
    # Account; the path should be set back to the default derivation path.
    acct.from_mnemonic( BIP39_ZOO )
    assert acct.path == "m/44'/144'/0'/0/0"  # Default
    assert acct.address == 'rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV'

    # And straight from BIP-39 Mnemonics
    details_zoos_using_bip39		= create(
        "SLIP39 Wallet: From zoo ... BIP-39",
        master_secret	= BIP39_ZOO,
    )
    [(eth_zoo,btc_zoo)]	= details_zoos_using_bip39.accounts
    btc_zoo.address == 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'


@pytest.mark.skipif( not scrypt or not eth_account,
                     reason="pip install slip39[wallet] to support private key encryption" )
def test_account_encrypt():
    """Ensure BIP-38 and Ethereum JSON wallet encryption and recovery works."""

    acct			= account( SEED_XMAS, crypto='Bitcoin' )
    assert acct.address == 'bc1qz6kp20ukkyx8c5t4nwac6g8hsdc5tdkxhektrt'
    assert acct.crypto == 'BTC'
    assert acct.path == "m/84'/0'/0'/0/0"
    assert acct.legacy_address() == "134t1ktyF6e4fNrJR8L6nXtaTENJx9oGcF"

    bip38_encrypted		= acct.encrypted( 'password' )
    assert bip38_encrypted == '6PYKmUhfJa5m1NR2zUaeHC3wUzGDmb1seSEgQHK7PK5HaVRHQSp7N4ytVf'

    acct_reco			= Account( crypto='Bitcoin' ).from_encrypted( bip38_encrypted, 'password' )
    assert acct_reco.address == 'bc1qz6kp20ukkyx8c5t4nwac6g8hsdc5tdkxhektrt'
    assert acct.crypto == 'BTC'
    assert acct.path == "m/84'/0'/0'/0/0"  # The default; assumed...
    assert acct_reco.legacy_address() == "134t1ktyF6e4fNrJR8L6nXtaTENJx9oGcF"

    acct			= account( SEED_XMAS, crypto='Ethereum' )
    assert acct.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'
    assert acct.crypto == 'ETH'
    assert acct.path == "m/44'/60'/0'/0/0"

    json_encrypted		= acct.encrypted( 'password' )
    assert json.loads( json_encrypted ).get( 'address' ) == '336cbeab83accdb2541e43d514b62dc6c53675f4'

    acct_reco			= Account( crypto='ETH' ).from_encrypted( json_encrypted, 'password' )
    assert acct_reco.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'
    assert acct.crypto == 'ETH'

    # Some test cases from https://en.bitcoin.it/wiki/BIP_0038

    # No compression, no EC multiply.  These tests produce the correct private key hex, but the
    # address hash verification check fails.  I suspect that they were actually created with a
    # *different* passphrase...
    assert Account( crypto='BTC' ).from_encrypted(
        '6PRVWUbkzzsbcVac2qwfssoUJAN1Xhrg6bNk8J7Nzm5H7kxEbn2Nh2ZoGg',
        'TestingOneTwoThree',
        strict=False,
    ).key.upper() == 'CBF4B9F70470856BB4F40F80B87EDB90865997FFEE6DF315AB166D713AF433A5'

    assert Account( crypto='BTC' ).from_encrypted(
        '6PRNFFkZc2NZ6dJqFfhRoFNMR9Lnyj7dYGrzdgXXVMXcxoKTePPX1dWByq',
        'Satoshi',
        strict=False,
    ).key.upper() == '09C2686880095B1A4C249EE3AC4EEA8A014F11E6F986D0B5025AC1F39AFBD9AE'

    # This weird UTF-8 test I cannot get to pass, regardless of what format I supply the passphrase in..

    # acct_reco			= Account( crypto='BTC' ).from_encrypted(
    #     '6PRW5o9FLp4gJDDVqJQKJFTpMvdsSGJxMYHtHaQBF3ooa8mwD69bapcDQn',
    #      bytes.fromhex('cf9300f0909080f09f92a9'), # '\u03D2\u0301\u0000\U00010400\U0001F4A9'
    # )
    # assert acct_reco.legacy_address() == '16ktGzmfrurhbhi6JGqsMWf7TyqK9HNAeF'

    # No compression, no EC multiply.  These test pass without relaxing the address hash verification check.
    assert Account( crypto='BTC' ).from_encrypted(
        '6PYNKZ1EAgYgmQfmNVamxyXVWHzK5s6DGhwP4J5o44cvXdoY7sRzhtpUeo',
        'TestingOneTwoThree'
    ).key.upper() == 'CBF4B9F70470856BB4F40F80B87EDB90865997FFEE6DF315AB166D713AF433A5'

    assert Account( crypto='BTC' ).from_encrypted(
        '6PYLtMnXvfG3oJde97zRyLYFZCYizPU5T3LwgdYJz1fRhh16bU7u6PPmY7',
        'Satoshi'
    ).key.upper() == '09C2686880095B1A4C249EE3AC4EEA8A014F11E6F986D0B5025AC1F39AFBD9AE'

    # Test some addresses encrypted by our Paper Wallet PDF output procedure, using
    # the "zoo zoo ... zoo wrong" BIP-39 test Mnemonic.
    assert Account( crypto='BTC' ).from_encrypted(
        '6PYSUhj4mPTNdSvm2dxLRszieSBmzPqPQX699ECUrd69sWteFAUqmW1FLq',
        'something'
    ).address == 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'

    # Ripple BIP-38 encrypted wallets.  Should round-trip via BIP-38 encryption
    acct_xrp		= Account( crypto='XRP' ).from_mnemonic( BIP39_ZOO )
    assert acct_xrp.path == "m/44'/144'/0'/0/0"  # Default
    assert acct_xrp.address == 'rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV'  # From Trezor "Model T" w/
    assert acct_xrp.pubkey == '039d65db4964cbf2049ad49467a6b73e7fec7d6e6f8a303cfbdb99fa21c7a1d2bc'
    acct_xrp_encrypted		= acct_xrp.encrypted( 'password' )
    assert acct_xrp_encrypted == '6PYTRxHt4sPM9i6zagBJ4pWdaefJ1FfVQwFCWQxDhVBw7fJYpYP3kMPfro'

    acct_dec			= Account( crypto='XRP' ).from_encrypted( acct_xrp_encrypted, 'password' )
    acct_dec.path == "m/44'/144'/0'/0/0"
    assert acct_dec.address == 'rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV'
    assert acct_dec.pubkey == '039d65db4964cbf2049ad49467a6b73e7fec7d6e6f8a303cfbdb99fa21c7a1d2bc'


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_create():
    """Standard SLIP-39 Mnemonic and account creation"""
    details_xmas		= create(
        "SLIP39 Wallet: Test",
        1,
        dict( fren = (3,5) ),
        SEED_XMAS
    )

    assert details_xmas.groups == {
        "fren": ( 3, [
            "academic agency academic acne academic academic academic academic academic academic academic academic academic academic academic academic academic arena diet involve",
            "academic agency academic agree closet maximum rumor beyond organize taught game helpful fishing brother bumpy nervous presence document buyer reject",
            "academic agency academic amazing arena meaning advocate hearing hunting pecan lilac device oasis teacher traffic retailer criminal scene flip true",
            "academic agency academic arcade cover acne safari item vanish else superior focus skin webcam venture clay loan various impact client",
            "academic agency academic axle carpet blimp stilt intend august racism webcam replace gather rich sweater mandate maximum rumor drink scene"
        ] ),
    }

    assert len(details_xmas.accounts) == 1
    [(eth,btc)] = details_xmas.accounts  # The default accounts created are ETH, BTC
    assert eth.address == '0x336cBeAB83aCCdb2541e43D514B62DC6C53675f4'
    assert btc.address == 'bc1qz6kp20ukkyx8c5t4nwac6g8hsdc5tdkxhektrt'

    assert recover( details_xmas.groups['fren'][1][:3] ) == SEED_XMAS

    # We can recover a slip39.Account directly from Mnemonics, too (default is native SLIP-39)
    assert account( '\n'.join( details_xmas.groups['fren'][1][:3] ), crypto='BTC' ).address == 'bc1qz6kp20ukkyx8c5t4nwac6g8hsdc5tdkxhektrt'

    # We know the native SLIP-39 and BIP-39 HD Wallet accounts for the 0xffff...ffff seed
    details_ones_native_slip39	= create(
        "SLIP39 Wallet: Native SLIP-39",
        1,
        dict( fren = (3,5) ),
        SEED_ONES
    )
    # We can recover a slip39.Account directly from Mnemonics, too (default is native SLIP-39)
    assert account( '\n'.join( details_ones_native_slip39.groups['fren'][1][:3] ), crypto='BTC' ).address == 'bc1q9yscq3l2yfxlvnlk3cszpqefparrv7tk24u6pl'

    details_ones_using_bip39	= create(
        "SLIP39 Wallet: Backup BIP-39",
        1,
        dict( fren = (3,5) ),
        SEED_ONES,
        using_bip39 = True,
    )
    # ... but recovery of "backup" of a BIP-39 via SLIP-39 is also directly supported:
    assert account( '\n'.join( details_ones_using_bip39.groups['fren'][1][:3] ), crypto='BTC', using_bip39=True ).address == 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'


@substitute( shamir_mnemonic.shamir, 'RANDOM_BYTES', nonrandom_bytes )
def test_create_bip39():
    """Standard SLIP-39 Mnemonic from BIP-39 backup and account creation.

    """
    details			= create(
        "SLIP39 Wallet: Test",
        1,
        dict( fren = (3,5) ),
        SEED_ONES,
        using_bip39	= True,
        cryptopaths	= ('ETH','BTC','XRP'),
    )

    assert len(details.accounts) == 1
    [(eth,btc,xrp)] = details.accounts
    # recognizable ETH, BTC accounts generated from the 0xffff...ffff (zoo zoo ...  wrong) Seed.
    assert eth.address == '0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E'
    assert btc.address == 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'
    assert xrp.address == 'rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV'


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
    #print( json.dumps( addrs, indent=4, default=str ))
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
    master_secret		= BIP39_ZOO
    addrgrps			= list( enumerate( addressgroups(
        master_secret	= master_secret,
        cryptopaths	= [
            ('ETH',	".../-3"),
            ('BTC',	".../-3"),
            ('LTC',	".../-3"),
            ('Doge',	".../-3"),
            ('Binance',	".../-3"),
            ('Ripple',	".../-3"),
        ],
    )))
    # print( repr( addrgrps ))
    assert addrgrps == [								# Verified
        (0,(('ETH', "m/44'/60'/0'/0/0", '0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E'),  # Ledger
            ('BTC', "m/84'/0'/0'/0/0", 'bc1qk0a9hr7wjfxeenz9nwenw9flhq0tmsf6vsgnn2'),   # Ledger
            ('LTC', "m/84'/2'/0'/0/0", 'ltc1qnreu4d88p5tvh33anptujvcvn3xmfhh43yg0am'),  # Ledger
            ('DOGE', "m/44'/3'/0'/0/0", 'DTMaJd8wqye1fymnjxZ5Cc5QkN1w4pMgXT'),	        # Ledger
            ('BSC', "m/44'/60'/0'/0/0", '0xfc2077CA7F403cBECA41B1B0F62D91B5EA631B5E'),  # Ledger
            ('XRP', "m/44'/144'/0'/0/0", 'rUPzi4ZwoYxi7peKCqUkzqEuSrzSRyLguV'))),       # Ledger
        (1, (('ETH', "m/44'/60'/0'/0/1", '0xd1a7451beB6FE0326b4B78e3909310880B781d66'),
             ('BTC', "m/84'/0'/0'/0/1", 'bc1qkd33yck74lg0kaq4tdcmu3hk4yruhjayxpe9ug'),
             ('LTC', "m/84'/2'/0'/0/1", 'ltc1qm4yc8vgxyv0xeu8p4vtq2wls245y2ueqpfrp4d'),
             ('DOGE', "m/44'/3'/0'/0/1", 'DGkL2LD5FfccAaKtx8G7TST5iZwrNkecTY'),
             ('BSC', "m/44'/60'/0'/0/1", '0xd1a7451beB6FE0326b4B78e3909310880B781d66'),
             ('XRP', "m/44'/144'/0'/0/1", 'ravkJwvQBuW4P5TG1qK5WDAgBxbPhdyPh1'))),
        (2, (('ETH', "m/44'/60'/0'/0/2", '0x578270B5E5B53336baC354756b763b309eCA90Ef'),
             ('BTC', "m/84'/0'/0'/0/2", 'bc1qvr7e5aytd0hpmtaz2d443k364hprvqpm3lxr8w'),
             ('LTC', "m/84'/2'/0'/0/2", 'ltc1qstkxz076qdyg0r08eszf0rrxsmfcgj62lkqaj2'),
             ('DOGE', "m/44'/3'/0'/0/2", 'DQa3SpFZH3fFpEFAJHTXZjam4hWiv9muJX'),
             ('BSC', "m/44'/60'/0'/0/2", '0x578270B5E5B53336baC354756b763b309eCA90Ef'),
             ('XRP', "m/44'/144'/0'/0/2", 'rpzdHCsqVLppnUAUvgYDd6ADZFeKE6QoHR'))),
        (3, (('ETH', "m/44'/60'/0'/0/3", '0x909f59835A5a120EafE1c60742485b7ff0e305da'),
             ('BTC', "m/84'/0'/0'/0/3", 'bc1q6t9vhestkcfgw4nutnm8y2z49n30uhc0kyjl0d'),
             ('LTC', "m/84'/2'/0'/0/3", 'ltc1qts5sde8st3x6qt2t0xhtf9uactg7nnztamuehk'),
             ('DOGE', "m/44'/3'/0'/0/3", 'DTW5tqLwspMY3NpW3RrgMfjWs5gnpXtfwe'),
             ('BSC', "m/44'/60'/0'/0/3", '0x909f59835A5a120EafE1c60742485b7ff0e305da'),
             ('XRP', "m/44'/144'/0'/0/3", 'r9czvGVozoKTAnP1G17RG9DfWK272ZExvX')))
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
