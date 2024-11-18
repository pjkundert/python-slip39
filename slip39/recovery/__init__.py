
#
# Python-slip39 -- Ethereum SLIP-39 Account Generation and Recovery
#
# Copyright (c) 2022, Dominion Research & Development Corp.
#
# Python-slip39 is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is also available under alternative (eg. Commercial) licenses, at
# your option.  See the LICENSE file at the top of the source tree.
#
# Python-slip39 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
from __future__		import annotations

import logging

from typing		import Dict, List, Optional, Union, Tuple, Sequence

from shamir_mnemonic	import group_ems_mnemonics, EncryptedMasterSecret, Share, MnemonicError
from shamir_mnemonic.shamir import RANDOM_BYTES

from mnemonic		import Mnemonic			# Requires passphrase as str
from ..util		import commas
from ..defaults		import BITS_DEFAULT
from .entropy		import (  # noqa F401
    shannon_entropy, signal_entropy, analyze_entropy, scan_entropy, display_entropy
)

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( __package__ )


def recover_encrypted(
    mnemonics: Sequence[Union[str,Share]],
    strict: bool = False,
) -> Tuple[EncryptedMasterSecret, Dict[int,Share], Sequence[int]]:
    """Recover encrypted SLIP-39 master secret Seed Entropy and Group details from the supplied
    SLIP-39 mnemonics.  Returns a sequence of EncryptedMasterSecret, and group Share detail that
    were used to resolve each one.

    We cannot know in advance what subset of these supplied mnemonics is required and/or valid, so
    we need to iterate over all subset combinations on failure; this allows us to recover from 1 (or
    more) incorrectly recovered SLIP-39 Mnemonics, using any others available.

    We'll try to find one of the smallest subset combinations that satisfies the SLIP-39 recovery.

    Use this method to recover but NOT decrypt the SLIP-39 master secret Seed.  Later, you may use
    this as a master_secret to slip39.create another set of SLIP-39 Mnemonics for this same
    passphrase-encrypted secret.

    """
    for ems, groups in group_ems_mnemonics( mnemonics, strict=strict ):
        log.info(
            f"Recovered {len(ems.ciphertext)*8}-bit Encrypted SLIP-39 Seed Entropy using {len(groups)} groups comprising {sum(map(len,groups.values()))} mnemonics"
        )
        yield ems, groups


def recover(
    mnemonics: List[Union[str,Share]],
    passphrase: Optional[Union[str,bytes]] = None,
    using_bip39: Optional[bool]	= None,  # If a BIP-39 "backup" (default: Falsey)
    as_entropy: Optional[bool]  = None,  # .. and recover original Entropy (not 512-bit Seed)
    language: Optional[str]	= None,  # ... provide BIP-39 language if not default 'english'
    strict: bool		= True,  # Fail if invalid Mnemonics are supplied
) -> bytes:
    """Recover, decrypt and return the (first) secret seed Entropy encoded in the SLIP-39 Mnemonics.

    If not 'using_bip39', the resultant secret Entropy is returned as the Seed, optionally with (not
    widely used) SLIP-39 decryption with the given passphrase (empty, if None).  We handle either
    str/bytes passphrase, and will en/decode as UTF-8 as necessary.

    WARNING: SLIP-39 passphrase encryption is not Trezor compatible, and is not widely used; if you
    want to hide a wallet, use the Trezor "Hidden wallet" feature instead, where the passphrase for
    each hidden wallet is entered on the device (leave this passphrase blank).

    Optionally, if 'using_bip39' then generate the actual 512-bit wallet Seed from the SLIP-39
    recovered 128- or 256-bit Seed Entropy, using standard BIP-39 Seed generation.

    This is the ideal way to back up an existing BIP-39 Mnemonic, I believe.  It results in a 20- or
    33-word SLIP-39 Mnemonics, retains any existing BIP-39 passphrase(s) defined by the user for
    securing the resultant Cryptocurrency wallet(s), and is compatible with all BIP-39 hardware
    wallets.  Once you are comfortable that you can always recover your BIP-39 Mnemonic from your
    SLIP-39 Mnemomnic Cards, you are free to destroy your original insecure and unreliable BIP-39
    Mnemonic backup(s).

    If strict, we will fail if invalid Mnemonics are supplied; otherwise, they'll be ignored.

    """
    try:
        encrypted_secret, groups = next( recover_encrypted( mnemonics, strict=strict ))
    except StopIteration:
        raise MnemonicError( "Invalid set of mnemonics; No encoded secret found" )

    # python-shamir-mnemonic requires passphrase as bytes (not str)
    if passphrase is None:
        passphrase		= ""
    passphrase_slip39		= b"" if using_bip39 else (
        passphrase if isinstance( passphrase, bytes ) else passphrase.encode( 'UTF-8' )
    )

    secret			= encrypted_secret.decrypt( passphrase_slip39 )

    log.info( "Seed decoded from SLIP-39" + (
        f" (w/ no passphrase) and generated using BIP-39 Mnemonic representation w/ {'a' if passphrase else 'no'} passphrase"
        if using_bip39 else
        f" Mnemonics w/ {'a' if passphrase else 'no'} passphrase"
    ))

    if using_bip39:
        # python-mnemonic's Mnemonic requires passphrase as str (not bytes).  This is all a NO-OP,
        # if using_bip39 is Truthy and as_entropy is Truthy, but no harm...  It checks that no
        # passphrase has been supplied in that case, as a side-effect.
        passphrase_bip39	= passphrase if isinstance( passphrase, str ) else passphrase.decode( 'UTF-8' )
        # This SLIP-39 was a "backup" of a BIP-39 Mnemonic, in a 'language' (default: "english").
        secret			= recover_bip39(
            mnemonic	= produce_bip39( entropy=secret, language=language ),
            passphrase	= passphrase_bip39,
            as_entropy	= as_entropy,
            language	= language,
        )
    return secret


def recover_bip39(
    mnemonic: str,
    passphrase: Optional[Union[str,bytes]] = None,
    as_entropy: Optional[bool]	= None,   # Recover original 128- or 256-bit Entropy (not 512-bit Seed)
    language: Optional[str]	= None,   # If desired, provide language (eg. if only prefixes are provided)
) -> bytes:
    """Recover the 512-bit BIP-39 generated seed (or the original 128- or 256-bit Seed Entropy, if
    as_entropy is True) from a single BIP-39 Mnemonic Phrase, detecting the language.  Optionally
    provide a UTF-8 string or encoded passphrase (defaults to not as_entropy, if so).

    Normalizes and validates the BIP-39 Mnemonic Phrase (which is often recovered as user input):
    - Removes excess whitespace and down-cases
    - Detects language if not provided
    - Expands unambiguous mnemonic prefixes (eg. 'ae' --> 'aerobic', 'acti' --> 'action')
    - Checks that the BIP-39 Phrase check bits are valid

    Since this would normally be used to begin deriving HD wallets, the default is the hashed,
    passphrase-decrypted seed.

    """
    if as_entropy is None:
        as_entropy		= False  # Default: recover the 512-bit derivation seed
    assert not ( bool( passphrase ) and bool( as_entropy )), \
        "When recovering original BIP-39 entropy, no passphrase may be specified"
    if passphrase is None:
        passphrase		= ""

    # Polish up the supplied mnemonic, by eliminating extra spaces, leading/trailing newline(s); Mnemonic is fragile...
    mnemonic_stripped		= ' '.join( w.lower() for w in mnemonic.strip().split( ' ' ) if w )
    if mnemonic_stripped != mnemonic:
        log.info( "BIP-39 Mnemonic Phrase stripped of unnecessary whitespace" )
    # Unfortunately, Mnemonic.detect_language was unreliable; only checked the first word and
    # english/french has ambiguous words (fixed in python-mnemonic versions >=0.20).  Mnemonic must
    # be able to unambiguously detect language with the first few un-expanded mnemonics.
    if not language:
        language		= Mnemonic.detect_language( mnemonic_stripped )
        log.info( f"BIP-39 Language detected: {language}" )
    m				= Mnemonic( language )
    mnemonic_expanded		= m.expand( mnemonic_stripped )
    if mnemonic_expanded != mnemonic_stripped:
        log.info( "BIP-39 Mnemonic Phrase prefixes expanded" )
    if not m.check( mnemonic_expanded ):
        unrecognized		= [ w for w in mnemonic_expanded.split() if w not in m.wordlist ]
        raise ValueError( f"BIP-39 Mnemonic check fails; {len( unrecognized )} unrecognized {m.language} words {commas( unrecognized )}" )
    if as_entropy or as_entropy is None:
        # If we want to "backup" a BIP-39 Mnemonic Phrase, we want the original entropy, NOT the derived seed!
        secret			= m.to_entropy( mnemonic_expanded )
        log.info( f"Recovered {len(secret)*8}-bit BIP-39 entropy from {language} mnemonic (no passphrase supported)" )
    else:
        # python-mnemonic's Mnemonic requires passphrase as str (not bytes)
        passphrase_bip39	= passphrase if isinstance( passphrase, str ) else passphrase.decode( 'UTF-8' )
        # Only a fully validated BIP-39 Mhemonic Phrase must ever be used here!  No checking is done
        # by Mnemonic.to_seed of either the Mnemonic Phrase or passphrase (except UTF-8 encoding).
        secret			= Mnemonic.to_seed( mnemonic_expanded, passphrase = passphrase_bip39 )
        log.info( f"Recovered {len(secret)*8}-bit BIP-39 secret from {language} mnemonic{' (and passphrase)' if passphrase_bip39 else ''}" )
    return bytes( secret )  # bytearray --> bytes


def produce_bip39(
    entropy: Optional[bytes],
    strength: Optional[int]	= None,
    language: Optional[str]	= None,
) -> str:
    """Produce a BIP-39 Mnemonic from the provided entropy (or generated, default 128 bits).

    We ensure we always use the same secure entropy source from shamir_mnemonic, to allow the user
    of slip39 to monkey-patch it in one place for testing or to improve the entropy generation.
    """
    if not entropy:
        if not strength:
            strength		= BITS_DEFAULT
        entropy			= RANDOM_BYTES( strength // 8 )
    return Mnemonic( language or "english" ).to_mnemonic( entropy )
