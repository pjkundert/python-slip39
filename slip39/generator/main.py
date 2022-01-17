import argparse
import codecs
import logging

from .			import chacha20poly1305, accountgroups_output, accountgroups_input
from ..util		import log_cfg, log_level, input_secure
from ..defaults		import BITS
from ..types		import Account
from ..api		import accountgroups, RANDOM_BYTES

log				= logging.getLogger( __package__ )


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Generate public wallet address(es) from a secret seed",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = """\
Once you have a secret seed (eg. from slip39.recovery), you can generate a sequence
of HD wallet addresses from it.  Emits rows in the form:

    <enumeration> [<address group(s)>]

If the output is to be transmitted by an insecure channel (eg. a serial port), which may insert
errors or allow leakage, it is recommended that the records be encrypted with a cryptographic
function that includes a message authentication code.  We use ChaCha20Poly1305 with a password and a
random nonce generated at program start time.  This is nonce is incremented for each record output.

Since the receiver requires the nonce to decrypt, and we do not want to separately transmit the
nonce and supply it to the receiver, the first record emitted when --encrypt is specified, is the
random nonce, encrypted with the password, with a known nonce of all 0 bytes.  The plaintext data is
random, while the nonce is not, but since this construction is only used once, it should be
satisfactory.

This first nonce record is transmitted with an enumeration prefix of "salt", if --enumerate is
specified.

""" )

    ap.add_argument( '-v', '--verbose', action="count",
                     default=0,
                     help="Display logging information." )
    ap.add_argument( '-q', '--quiet', action="count",
                     default=0,
                     help="Reduce logging output." )
    ap.add_argument( '-s', '--secret',
                     default=None,
                     help="Use the supplied 128-, 256- or 512-bit hex value as the secret seed; '-' (default) reads it from stdin (eg. output from slip39.recover)" )
    ap.add_argument( '-c', '--cryptocurrency', action='append',
                     default=None,
                     help="A crypto name and optional derivation path (default: \"ETH:{Account.path_default('ETH')}\"), optionally w/ ranges, eg: ETH:m/40'/66'/0'/0/-" )
    ap.add_argument( '-a', '--address',
                     default=None,
                     help="Modify all cryptocurrency paths by replacing the final address segment w/ the supplied range, eg. '-', meaning [0,...)")
    ap.add_argument( '-b', '--baudrate',
                     default='',
                     help="Set the baud rate of the serial device (default: 115200)" )
    ap.add_argument( '-e', '--encrypt',
                     default='',
                     help="Secure the channel from errors and/or prying eyes with ChaCha20Poly1305 encryption w/ this password; '-' reads from stdin" )
    ap.add_argument( '--decrypt', dest="encrypt" )
    ap.add_argument( '--enumerated', action='store_true',
                     default=True,
                     help="Include an enumeration in each record output (required for --encrypt)" )
    ap.add_argument( '--no-enumerate', dest="enumerate", action='store_false',
                     help="Disable enumeration of output records" )
    ap.add_argument( '--receive', action='store_true',
                     default=False,
                     help="Receive a stream of slip.generator output" )
    ap.add_argument( '--corrupt',
                     default=False,
                     help="Corrupt a percentage of output symbols" )

    args			= ap.parse_args( argv )

    log_cfg['level']		= log_level( args.verbose - args.quiet )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )
    logging.debug( f"{args}" )

    # Confirm sanity of args
    assert not args.encrypt or args.enumerate, \
        "When --encrypt is specified, --enumerated is required"
    assert not args.receive or not ( args.address or args.secret ), \
        "When --receive, no --address nor --secret allowed"

    # Master secret seed supplied as hex
    secret			= None
    if not args.receive:
        secret			= args.secret or '-'
        if secret == '-':
            secret		= input_secure( 'Master secret hex: ', secret=True )
        else:
            log.warning( "It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input" )
        if secret.lower().startswith('0x'):
            secret		= secret[2:]
        secret			= codecs.decode( secret, 'hex_codec' )
        secret_bits		= len( secret ) * 8
        if secret_bits not in BITS:
            raise ValueError( f"A {secret_bits}-bit master secret was supplied; One of {BITS!r} expected" )

    # Create cipher if necessary
    cipher,nonce		= None,None
    encrypt			= args.encrypt
    if encrypt == '-':
        encrypt			= input_secure( 'Encryption password: ', secret=True )
    if encrypt:
        cipher			= chacha20poly1305( password=encrypt )
        if not args.receive:
            # On --receive, we will read the encrypted nonce from the sender
            nonce		= RANDOM_BYTES( 12 )

    if args.receive:
        # Receive groups, ignoring any that cannot be parsed.  Add the enumeration
        # to the nonce for decrypting.
        for index,group in accountgroups_input( cipher=cipher ):
            accountgroups_output( group, index=index )
        return 0

    # ...else...
    # Transmitting.
    cryptopaths			= []
    for crypto in args.cryptocurrency or ['ETH', 'BTC']:
        try:
            crypto,paths	= crypto.split( ':' )
        except ValueError:
            crypto,paths	= crypto,None
        crypto			= Account.supported( crypto )
        if paths is None:
            paths		= Account.path_default( crypto )
        if args.address:
            path_segs		= paths.split( '/' )
            path_segs[-1]	= args.address + ( "'" if ( "'" in path_segs[-1] and "'" not in args.address ) else "" )
            paths		= '/'.join( path_segs )
        cryptopaths.append( (crypto,paths) )

    for index,group in enumerate( accountgroups(
        master_secret	= secret,
        cryptopaths	= cryptopaths,
    )):
        accountgroups_output(
            group	= group,
            index	= index if args.enumerated else None,
            cipher	= cipher,
            nonce	= nonce,
            corrupt	= float( args.corrupt ) if args.corrupt else 0,
        )

    return 0
