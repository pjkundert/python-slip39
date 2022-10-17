
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

import itertools
import logging

from typing		import List, Optional

from shamir_mnemonic	import combine_mnemonics
from mnemonic		import Mnemonic

from ..util		import ordinal

from .entropy		import (  # noqa F401
    shannon_entropy, signal_entropy, analyze_entropy, scan_entropy, display_entropy
)

log				= logging.getLogger( __package__ )


def recover(
    mnemonics: List[str],
    passphrase: bytes		= b"",
    using_bip39: bool		= False,
) -> bytes:
    """Recover a master secret Seed Entropy from the supplied SLIP-39 mnemonics.  We cannot know what
    subset of these mnemonics is required and/or valid, so we need to iterate over all subset
    combinations on failure.

    We'll try to find one of the smallest subsets that satisfies the SLIP-39 recovery.  The
    resultant secret Entropy is returned as the Seed, with (not widely used) SLIP-39 decryption with
    the given passphrase.

    WARNING: SLIP-39 passphrase encryption is not Trezor "Model T" compatible, and is not widely
    used; if you want to hide a wallet, use the Trezor "Hidden wallet" feature instead, where the
    passphrase for each hidden wallet is entered on the device (leave this passphrase blank).

    Optionally, if using_bip39 then generate the Seed from the recovered Seed Entropy, using BIP-39
    Seed generation.  This is the ideal way to back up an existing BIP-39 Mnemonic, I believe.  It
    results in a 20- or 33-word SLIP-39 Mnemonics, retains the BIP-39 passphrase(s) for securing the
    resultant Cryptocurrency wallet(s), and is compatible with all BIP-39 hardware wallets.  Once
    you are comfortable that you can always recover your BIP-39 Mnemonic from your SLIP-39 Mnemomnic
    Cards, you are free to destroy your original insecure and unreliable BIP-39 Mnemonic backup(s).

    """
    secret			= None
    try:
        combo			= range( len( mnemonics ))
        secret			= combine_mnemonics(
            mnemonics,
            passphrase	= b"" if using_bip39 else passphrase
        )
    except Exception as exc:
        # Try a subset of the supplied mnemonics, to silently reject any invalid mnemonic phrases supplied
        for length in range( len( mnemonics )):
            for combo in itertools.combinations( range( len( mnemonics )), length ):
                trial		= list( mnemonics[i] for i in combo )
                try:
                    secret	= combine_mnemonics(
                        trial,
                        passphrase	= b"" if using_bip39 else passphrase
                    )
                    break
                except Exception:
                    pass
            if secret:
                break
        if not secret:
            # No recovery; raise the Exception produced by original attempt w/ all mnemonics
            raise exc
    log.info(
        f"Recovered {len(secret)*8}-bit SLIP-39 Seed Entropy with {len(combo)}"
        f" ({'all' if len(combo) == len(mnemonics) else ', '.join( ordinal(i+1) for i in combo)})"
        f" of {len(mnemonics)} supplied mnemonics" + (
            f"; Seed decoded from SLIP-39 (w/ no passphrase) and generated using BIP-39 Mnemonic representation w/ {'a' if passphrase else 'no'} passphrase"
            if using_bip39 else
            f"; Seed decoded from SLIP-39 Mnemonics w/ {'a' if passphrase else 'no'} passphrase"
        )
    )
    if using_bip39:
        secret			= recover_bip39(
            mnemonic	= produce_bip39( entropy=secret ),
            passphrase	= passphrase,
        )
    return secret


def recover_bip39(
    mnemonic: str,
    passphrase: bytes		= b"",
    as_entropy			= False,  # Recover original 128- or 256-bit Entropy (not 512-bit Seed)
) -> bytes:
    """Recover a secret 512-bit BIP-39 generated seed (or just the original 128- or 256-bit entropy)
    from a single BIP-39 mnemonic phrase, detecting the language.

    """
    assert not ( bool( passphrase ) and bool( as_entropy )), \
        "When recovering original BIP-39 entropy, no passphrase may be specified"
    # Polish up the supplied mnemonic, by eliminating extra spaces; Mnemonic is fragile...
    mnemonic			= ' '.join( w.lower() for w in mnemonic.split( ' ' ) if w )
    # Unfortunately, Mnemonic.detect_language was unreliable; only checked the first word
    # and english/french has ambiguous words. TODO: check if python-mnemonic has been fixed.
    last			= ValueError( "Empty mnemonic" )
    for word in mnemonic.split( ' ' ):
        try:
            language		= Mnemonic.detect_language( word )
            m			= Mnemonic( language )
            assert m.check( mnemonic ), \
                f"Invalid {language} mnemonic: {mnemonic!r}"
            if as_entropy:
                secret		= m.to_entropy( mnemonic )
            else:
                secret		= Mnemonic.to_seed( mnemonic, passphrase )
            log.info( f"Recovered {len(secret)*8}-bit BIP-39 secret from {language} mnemonic" )
            return bytes( secret )  # bytearray --> bytes
        except Exception as exc:
            last		= exc
    raise last


def produce_bip39(
    entropy: Optional[bytes],
    strength: Optional[int]	= None,
    language: str		= "english",
) -> str:
    """Produce a BIP-38 Mnemonic from the provided entropy (or generated, default 128 bits)."""
    mnemo			= Mnemonic( language )
    if entropy:
        return mnemo.to_mnemonic( entropy )
    return mnemo.generate( strength or 128 )
