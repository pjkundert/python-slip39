import itertools
import logging

from typing		import List

from shamir_mnemonic	import combine_mnemonics

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
    log.warning( f"Recovered SLIP-39 secret with {len(combo)}"
                 f" ({'all' if len(combo) == len(mnemonics) else ', '.join( ordinal(i+1) for i in combo)}) "
                 f"of {len(mnemonics)} supplied mnemonics" )
    return secret