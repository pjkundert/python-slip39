import argparse
import codecs
import logging

from .api		import random_secret
from .util		import log_cfg, log_level, input_secure
from .layout		import write_pdfs
from .types		import Account
from .defaults		import (   # noqa: F401
    CARD, CARD_SIZES, PAPER,
    BITS, BITS_DEFAULT,
    FILENAME_FORMAT,
    FILENAME_KEYWORDS,
    CRYPTO_PATHS,
)

log				= logging.getLogger( __package__ )


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Create and output SLIP39 encoded Ethereum wallet(s) to a PDF file.",
        epilog = "" )
    ap.add_argument( '-v', '--verbose', action="count",
                     default=0,
                     help="Display logging information." )
    ap.add_argument( '-q', '--quiet', action="count",
                     default=0,
                     help="Reduce logging output." )
    ap.add_argument( '-o', '--output',
                     default=FILENAME_FORMAT,
                     help="Output PDF to file or '-' (stdout); formatting w/ {', '.join( FILENAME_KEYWORDS )} allowed" )
    ap.add_argument( '-t', '--threshold',
                     default=None,
                     help="Number of groups required for recovery (default: half of groups, rounded up)" )
    ap.add_argument( '-g', '--group', action='append',
                     help="A group name[[<require>/]<size>] (default: <size> = 1, <require> = half of <size>, rounded up, eg. 'Frens(3/5)' )." )
    ap.add_argument( '-f', '--format', action='append',
                     default=[],
                     help=f"Specify default crypto address formats: {', '.join( Account.FORMATS )}; default {', '.join( f'{c}:{Account.address_format(c)}' for c in Account.CRYPTOCURRENCIES)}" )
    ap.add_argument( '-c', '--cryptocurrency', action='append',
                     default=[],
                     help=f"A crypto name and optional derivation path ('../<range>/<range>' allowed); defaults: {', '.join( f'{c}:{Account.path_default(c)}' for c in Account.CRYPTOCURRENCIES)}" )
    ap.add_argument( '-j', '--json',
                     default=None,
                     help="Save an encrypted JSON wallet for each Ethereum address w/ this password, '-' reads it from stdin (default: None)" )
    ap.add_argument( '-s', '--secret',
                     default=None,
                     help="Use the supplied 128-, 256- or 512-bit hex value as the secret seed; '-' reads it from stdin (eg. output from slip39.recover)" )
    ap.add_argument( '--bits',
                     default=None,  # Do not enforce default of 128-bit seeds
                     help=f"Ensure that the seed is of the specified bit length; {', '.join( map( str, BITS ))} supported." )
    ap.add_argument( '--passphrase',
                     default=None,
                     help="Encrypt the master secret w/ this passphrase, '-' reads it from stdin (default: None/'')" )
    ap.add_argument( '-C', '--card',
                     default=None,
                     help=f"Card size; {', '.join(CARD_SIZES.keys())} or '(<h>,<w>),<margin>' (default: {CARD})" )
    ap.add_argument( '--paper',
                     default=None,
                     help=f"Paper size (default: {PAPER})" )
    ap.add_argument( '--no-card', dest="card", action='store_false',
                     help="Disable PDF SLIP-39 mnemonic card output" )
    ap.add_argument( '--text', action='store_true',
                     default=None,
                     help="Enable textual SLIP-39 mnemonic output to stdout" )
    ap.add_argument( 'names', nargs="*",
                     help="Account names to produce")
    args			= ap.parse_args( argv )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    log_cfg['level']		= log_level( args.verbose - args.quiet )
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    # If any --format <crypto>:<format> address formats provided
    for cf in args.format:
        try:
            Account.address_format( *cf.split( ':' ) )
        except Exception as exc:
            log.error( f"Invalid address format: {cf}: {exc}" )
            raise

    bits_desired		= int( args.bits ) if args.bits else BITS_DEFAULT

    master_secret		= args.secret
    if master_secret:
        # Master secret seed supplied as hex
        if master_secret == '-':
            master_secret	= input_secure( 'Master secret hex: ', secret=True )
        else:
            log.warning( "It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input" )
        if master_secret.lower().startswith('0x'):
            master_secret	= master_secret[2:]
        master_secret		= codecs.decode( master_secret, 'hex_codec' )
    else:
        # Generate a random secret seed
        master_secret		= random_secret( bits_desired // 8 )
    master_secret_bits		= len( master_secret ) * 8
    if master_secret_bits not in BITS:
        raise ValueError( f"A {master_secret_bits}-bit master secret was supplied; One of {BITS!r} expected" )
    if args.bits and master_secret_bits != bits_desired:  # If a certain seed size specified, enforce
        raise ValueError( f"A {master_secret_bits}-bit master secret was supplied, but {bits_desired} bits was specified" )

    # Optional passphrase
    passphrase			= args.passphrase or ""
    if passphrase == '-':
        passphrase		= input_secure( 'Master seed passphrase: ', secret=True )
    elif passphrase:
        log.warning( "It is recommended to not use '-p|--passphrase <password>'; specify '-' to read from input" )

    try:
        write_pdfs(
            names		= args.names,
            master_secret	= master_secret,
            passphrase		= passphrase,
            group		= args.group,
            threshold		= args.threshold,
            cryptocurrency	= args.cryptocurrency,
            card		= args.card,
            paper		= args.paper,
            filename		= args.output,
            json_pwd		= args.json,
            text		= args.text,
        )
    except Exception as exc:
        log.exception( f"Failed to write PDFs: {exc}" )
        return 1
    return 0
