import argparse
import codecs
import logging
import sys

from ..util		import log_cfg, log_level, input_secure, ordinal
from .			import recover, recover_bip39

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

BIP-39 wallets can be backed up as SLIP-39 wallets, but only at the cost of 59-word SLIP-39
mnemonics.  This is because the *output* 512-bit BIP-39 seed must be stored in SLIP-39 -- not the
*input* 128-, 160-, 192-, 224-, or 256-bi entropy used to create the original BIP-39 mnemonic
phrase.

""" )

    ap.add_argument( '-v', '--verbose', action="count",
                     default=0,
                     help="Display logging information." )
    ap.add_argument( '-q', '--quiet', action="count",
                     default=0,
                     help="Reduce logging output." )
    ap.add_argument( '-b', '--bip39', action='store_true',
                     default=None,
                     help="Recover 512-bit secret seed from BIP-39 mnemonics" )
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
    passphrase			= passphrase.encode( 'utf-8' )

    # If BIP-39 recovery designated, only a single mnemonic is allowed:
    secret			= None
    algo			= "SLIP-39" if args.bip39 is None else "BIP-39"
    mnemonics			= args.mnemonic or []
    if args.bip39:
        assert 0 <= len( mnemonics ) <= 1, "BIP-39 requires exactly one mnemonic"
        if not mnemonics:
            try:
                phrase		= input_secure( f"Enter {ordinal(len(mnemonics)+1)} {algo} mnemonic: ", secret=False )
            except KeyboardInterrupt:
                return 0
            mnemonics.append( phrase )
        try:
            secret		= recover_bip39( *mnemonics, passphrase )
        except KeyboardInterrupt:
            return 0
        except Exception as exc:
            log.error( f"Could not recover {algo} seed with supplied mnemonic: {exc}" )
    else:
        # Collect more mnemonics 'til we can successfully recover the master secret seed
        while secret is None:
            try:
                secret		= recover( mnemonics, passphrase )
            except KeyboardInterrupt:
                return 0
            except Exception as exc:
                if mnemonics:
                    log.info( f"Could not recover {algo} seed with {len(mnemonics)} supplied mnemonics: {exc}" )
                try:
                    phrase	= input_secure( f"Enter {ordinal(len(mnemonics)+1)} {algo} mnemonic: ", secret=False )
                except KeyboardInterrupt:
                    return 0
                if ':' in phrase:  # Discard any "<name>: <mnemonic>" name prefix.
                    _,phrase	= phrase.split( ':', 1 )
                mnemonics.append( phrase )
    if secret:
        secret			= codecs.encode( secret, 'hex_codec' ).decode( 'ascii' )
        log.info( "Recovered {algo} secret; To re-generate SLIP-39 wallet, send it to: python3 -m slip39 --secret -" )
        print( secret )
    return 0 if secret else 1


if __name__ == "__main__":
    sys.exit( main() )
