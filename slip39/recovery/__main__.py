import argparse
import codecs
import logging
import sys

from ..util		import log_cfg, log_level, input_secure, ordinal
from .			import recover

log				= logging.getLogger( __package__ )


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Recover and output SLIP39 encoded Ethereum wallet(s) to a PDF file.",
        epilog = """\
If you obtain a threshold number of SLIP-39 mnemonics, you can recover the original
secret seed, and re-generate one or more Ethereum wallets from it.

Enter the mnemonics when prompted and/or via the command line with -m |--mnemonic "...".

The master secret seed can then be used to generate a new SLIP-39 encoded wallet:

    python3 -m slip39 --secret = "ab04...7f"
""" )

    ap.add_argument( '-v', '--verbose', action="count",
                     default=0,
                     help="Display logging information." )
    ap.add_argument( '-q', '--quiet', action="count",
                     default=0,
                     help="Reduce logging output." )
    ap.add_argument( '-m', '--mnemonic', action='append',
                     help="Supply another SLIP-39 mnemonic phrase" )
    ap.add_argument( '-p', '--passphrase',
                     default=None,
                     help="Encrypt the master secret w/ this passphrase, '-' reads it from stdin (default: None/'')" )
    args			= ap.parse_args( argv )

    log_cfg['level']		= log_level( args.verbose - args.quiet )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    # Optional passphrase (utf-8 encoded bytes)
    passphrase			= args.passphrase or ""
    if passphrase == '-':
        passphrase		= input_secure( 'Master seed passphrase: ', secret=True )
    elif passphrase:
        log.warning( "It is recommended to not use '-p|--passphrase <password>'; specify '-' to read from input" )

    # Collect more mnemonics 'til we can successfully recover the master secret seed
    mnemonics			= args.mnemonic or []
    secret			= None
    while secret is None:
        try:
            secret		= recover( mnemonics, passphrase.encode( 'utf-8' ))
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            if mnemonics:
                log.info( f"Could not recover SLIP-39 master secret with {len(mnemonics)} supplied mnemonics: {exc}" )
            phrase		= input_secure( f"Enter {ordinal(len(mnemonics)+1)} SLIP-39 mnemonic: ", secret=False )
            if ':' in phrase:  # Discard any "<name>: <mnemonic>" name prefix.
                _,phrase	= phrase.split( ':', 1 )
            mnemonics.append( phrase )
    if secret:
        secret			= codecs.encode( secret, 'hex_codec' ).decode( 'ascii' )
        log.info( "Recovered SLIP-39 secret; To re-generate, send it to: python3 -m slip39 --secret -" )
        print( secret )
    return 0


if __name__ == "__main__":
    sys.exit( main() )
