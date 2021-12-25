import argparse
import codecs
import getpass
import logging
import sys

from ..util		import log_cfg, ordinal
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
    ap.add_argument( '-m', '--mnemonic', action='append',
                     help="Supply another SLIP-39 mnemonic phrase" )
    ap.add_argument( '-p', '--passphrase',
                     default=None,
                     help="Encrypt the master secret w/ this passphrase, '-' reads it from stdin (default: None/'')" )
    args			= ap.parse_args( argv )

    levelmap 			= {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    log_cfg['level']		= levelmap[args.verbose] if args.verbose in levelmap else logging.DEBUG
    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    # Optional passphrase (utf-8 encoded bytes)
    passphrase			= args.passphrase or ""
    if passphrase == '-':
        passphrase		= getpass.getpass( 'Master seed passphrase: ' )
    elif passphrase:
        log.warning( "It is recommended to not use '-p|--passphrase <password>'; specify '-' to read from input" )

    # Collect mnemonics 'til we can successfully recover the master secret seed

    mnemonics			= args.mnemonic or []
    master_secret		= None
    while master_secret is None:
        try:
            master_secret	= recover( mnemonics, passphrase.encode( 'utf-8' ))
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            if mnemonics:
                log.info( f"Could not recover SLIP-39 master secret with {len(mnemonics)} supplied mnemonics: {exc}" )
            mnemonics.append( input( f"Enter {ordinal(len(mnemonics)+1)} SLIP-39 mnemonic: " ))
    if master_secret:
        secret			= codecs.encode( master_secret, 'hex_codec' ).decode( 'ascii' )
        log.warning( "Recovered SLIP-39 secret; Use: python3 -m slip39 --secret ..." )
        print( secret )
    return 0

if __name__ == "__main__":
    sys.exit( main() )
