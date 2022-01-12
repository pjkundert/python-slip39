import argparse
import codecs
import json
import logging
import sys

from ..util		import log_cfg, log_level, input_secure
from ..defaults		import BITS
from ..generate		import accountgroups

log				= logging.getLogger( __package__ )


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Generate public wallet address(es) from a secret seed",
        epilog = """\
Once you have a secret seed (eg. from slip39.recovery), you can generate a sequence
of HD wallet addresses from it.

""" )

    ap.add_argument( '-v', '--verbose', action="count",
                     default=0,
                     help="Display logging information." )
    ap.add_argument( '-q', '--quiet', action="count",
                     default=0,
                     help="Reduce logging output." )
    ap.add_argument( '-s', '--secret',
                     default='-',
                     help="Use the supplied 128-, 256- or 512-bit hex value as the secret seed; '-' (default) reads it from stdin (eg. output from slip39.recover)" )
    ap.add_argument( '-c', '--cryptocurrency', action='append',
                     default=None,
                     help="A crypto name and optional derivation path (default: \"ETH:{DEFAULT_PATH('ETH')}\"), optionally w/ ranges, eg: ETH:m/40'/66'/0'/0/-" )
    ap.add_argument( '-a', '--account',
                     default=None,
                     help="Modify any default cryptocurrency paths by replacing the account section w/ the supplied range" )
    ap.add_argument( '-e', '--enumerated', action='store_true',
                     default=False,
                     help="Include an enumeration in each record output" )
    args			= ap.parse_args( argv )

    log_cfg['level']		= log_level( args.verbose - args.quiet )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )
    logging.debug( f"{args}" )
    # Master secret seed supplied as hex
    secret			= args.secret
    if secret == '-':
        secret			= input_secure( 'Master secret hex: ', secret=True )
    else:
        log.warning( "It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input" )
    if secret.lower().startswith('0x'):
        secret			= secret[2:]
    secret			= codecs.decode( secret, 'hex_codec' )
    secret_bits			= len( secret ) * 8
    if secret_bits not in BITS:
        raise ValueError( f"A {secret_bits}-bit master secret was supplied; One of {BITS!r} expected" )

    cryptopaths			= []
    for crypto in args.cryptocurrency or ['ETH']:
        try:
            crypto,paths	= crypto.split( ':' )
        except ValueError:
            crypto,paths	= crypto,None
        cryptopaths.append( (crypto,paths) )

    count			= 0
    for accts in accountgroups(
        master_secret	= secret,
        cryptopaths	= cryptopaths,
    ):
        record	= [
            (acct._cryptocurrency.SYMBOL, acct.path, acct.address)
            for acct in accts
        ]
        if args.enumerated:
            record	= ( count, record )
            count      += 1
        print( json.dumps( record ))


if __name__ == "__main__":
    sys.exit( main() )
