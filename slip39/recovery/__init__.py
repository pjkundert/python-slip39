import itertools
import logging

from typing		import List, Optional

from shamir_mnemonic	import combine_mnemonics
from mnemonic		import Mnemonic

from ..util		import ordinal
log				= logging.getLogger( __package__ )


def recover(
    mnemonics: List[str],
    passphrase: bytes		= b"",
) -> bytes:
    """Recover a master secret from the supplied SLIP-39 mnemonics.  We cannot know what subset of
    these mnemonics is required and/or valid, so we need to iterate over all subset combinations on
    failure.

    We'll try to find the smallest subset that satisfies the SLIP39 recovery.

    """
    secret			= None
    try:
        combo			= range( len( mnemonics ))
        secret			= combine_mnemonics( mnemonics, passphrase=passphrase )
    except Exception as exc:
        # Try a subset of the supplied mnemonics, to silently reject any invalid mnemonic phrases supplied
        for length in range( len( mnemonics )):
            for combo in itertools.combinations( range( len( mnemonics )), length ):
                trial		= list( mnemonics[i] for i in combo )
                try:
                    secret	= combine_mnemonics( trial, passphrase=passphrase )
                    break
                except Exception:
                    pass
            if secret:
                break
        if not secret:
            # No recovery; raise the Exception produced by original attempt w/ all mnemonics
            raise exc
    log.warning( f"Recovered {len(secret)*8}-bit SLIP-39 secret with {len(combo)}"
                 f" ({'all' if len(combo) == len(mnemonics) else ', '.join( ordinal(i+1) for i in combo)}) "
                 f"of {len(mnemonics)} supplied mnemonics" )
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
    language			= Mnemonic.detect_language( mnemonic )
    m				= Mnemonic( language )
    # Polish up the supplied mnemonic, by eliminating extra spaces; Mnemonic is fragile...
    mnemonic			= ' '.join( w.lower() for w in mnemonic.split( ' ' ) if w )
    assert m.check( mnemonic ), \
        f"Invalid BIP-39 mnemonic: {mnemonic}"
    if as_entropy:
        secret			= m.to_entropy( mnemonic )
    else:
        secret			= Mnemonic.to_seed( mnemonic, passphrase )
    log.warning( f"Recovered {len(secret)*8}-bit BIP-39 secret from {language} mnemonic" )
    return bytes( secret )  # bytearray --> bytes


def produce_bip39(
    entropy: Optional[bytes],
    strength: Optional[int]	= None,
    language: str		= "english",
):
    """Produce a BIP-38 Mnemonic from the provided entropy (or generated, default 128 bits)."""
    mnemo			= Mnemonic( language )
    if entropy:
        return mnemo.to_mnemonic( entropy )
    return mnemo.generate( strength or 128 )
