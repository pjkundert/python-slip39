import itertools
import logging

from typing			import List

from shamir_mnemonic		import combine_mnemonics

log				= logging.getLogger( __package__ )


def recover(
    mnemonics: List[str],
    passphrase: bytes		= b"",
) -> bytes:
    """Recover a master secret from the supplied SLIP-39 mnemonics.  We cannot know what subset of
    these mnemonics is required and/or valid, so we need to iterate over all subset combinations on
    failure.

    """
    try:
        return combine_mnemonics( mnemonics, passphrase=passphrase )
    except Exception as exc:
        # Try a subset of the supplied mnemonics, to silently reject any invalid phrases
        for n in range( len( mnemonics ), 0, -1 ):
            for c in itertools.combinations( mnemonics, n ):
                m			= list( c )
                try:
                    return combine_mnemonics( m, passphrase=passphrase )
                except Exception:
                    pass
                else:
                    log.info( f"Recovered SLIP-39 master secrete with {len(m)} of {len(mnemonics)} supplied mnemonics" )
        raise exc
