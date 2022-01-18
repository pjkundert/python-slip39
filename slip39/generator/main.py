import argparse
import codecs
import logging
import time

from serial		import Serial

from .			import chacha20poly1305, accountgroups_output, accountgroups_input, file_outputline
from ..util		import log_cfg, log_level, input_secure
from ..defaults		import BITS, BAUDRATE
from ..types		import Account, path_edit
from ..api		import accountgroups, RANDOM_BYTES

log				= logging.getLogger( __package__ )

class SerialEOF( Serial ):
    """Converts Serial exceptions into EOFError, for compatibility w/ expectations of file-like objects.

    """
    def read( self, size=1 ):
        while True:
            try:
                return super( SerialEOF, self ).read( size=size )
            except Exception as exc:  # SerialError as exc:
                # if "readiness" in str(exc):
                #     time.sleep( .1 )
                #     continue
                raise EOFError( str( exc ))

def serial_flow( ser ):
    dsr				= ser.dsr		# Do we output DSR and expect DTR?
    dtr				= ser.dtr		#   and what is our current DTR?
    rts				= ser.rts		# Do we output RTS and expect CTS
    cts				= ser.cts		#   and what is our current CTS?
    return (dsr,dtr),(rts,cts)


def serial_status( dsrdtr, rtscts ):
    dsr,dtr		= dsrdtr
    rts,cts		= rtscts
    return ( f"DSR --> {'1' if dsr else 'x'} / DTR <-- {'1' if dtr else 'x'},"
             + f" RTS --> {'1' if rts else 'x'} / CTS <-- {'1' if cts else 'x'}"
             + ( "" if cts else "; Receiver full " )
             + ( "" if dtr else "; Receiver not connected " ))


def serial_connected( ser ):
    """Detect if the serial port is connected by monitoring DSR/DTR. """
    flow			= serial_flow( ser )
    (dsr,dtr),(rts,cts)		= flow
    health			= dsr and dtr
    if health:
        log.info( f"{ser!r:.36}: {serial_status( *flow )}; Healthy" )
    else:
        log.warning( f"{ser!r:.36}: {serial_status( *flow )}; Unhealthy; missing DSR and/or DTR" )

    return health


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
random nonce generated at program start time.  This nonce is incremented for each record output.

Since the receiver requires the nonce to decrypt, and we do not want to separately transmit the
nonce and supply it to the receiver, the first record emitted when --encrypt is specified is the
random nonce, encrypted with the password, itself with a known nonce of all 0 bytes.  The plaintext
data is random, while the nonce is not, but since this construction is only used once, it should be
satisfactory.  This first nonce record is transmitted with an enumeration prefix of "nonce".


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
    ap.add_argument( '-f', '--format', action='append',
                     default=[],
                     help=f"Specify default crypto address formats: {', '.join( Account.FORMATS )}; default {', '.join( f'{c}:{Account.address_format(c)}' for c in Account.CRYPTOCURRENCIES)}" )
    ap.add_argument( '-c', '--cryptocurrency', action='append',
                     default=[],
                     help="A crypto name and optional derivation path (default: \"ETH:{Account.path_default('ETH')}\"), optionally w/ ranges, eg: ETH:../0/-" )
    ap.add_argument( '-p', '--path',
                     default=None,
                     help="Modify all derivation paths by replacing the final segment(s) w/ the supplied range(s), eg. '.../1/-' means .../1/[0,...)")
    ap.add_argument( '-d', '--device', type=str,
                     default=None,
                     help="Use this serial device to transmit (or --receive) records" )
    ap.add_argument( '-b', '--baudrate', type=int,
                     default=None,
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

    # Confirm sanity of args
    assert not args.encrypt or args.enumerate, \
        "When --encrypt is specified, --enumerated is required"
    assert not args.receive or not ( args.path or args.secret ), \
        "When --receive, no --path nor --secret allowed"
    if args.path:
        assert args.path.lstrip( '.' ).startswith( '/' ), \
            f"A --path must start with '../', indicating intent to replace 1 or more trailing components of each cryptocurrency's derivation path"

    # If any --format <crypto>:<format> address formats provided
    for cf in args.format:
        try:
            Account.address_format( *cf.split( ':' ) )
        except Exception as exc:
            log.error( f"Invalid address format: {cf}: {exc}" )
            raise

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
        file			= None
        encoding		= None
        healthy			= serial_connected
        if args.device:
            # Await the appearance of a healthy connection to a live (DTR-asserting) peer.
            health		= False
            while not health:
                encoding	= 'UTF-8'
                file		= Serial(
                    port	= args.device,
                    baudrate	= args.baudrate or BAUDRATE,
                    xonxoff	= False,
                    rtscts	= True,
                    dsrdtr	= True,
                    timeout	= 1/10,		# Re-inspect port every so often on incomplete reads
                )

                # Ensure counterparty has time to recognize we have restarted
                file.dtr	= False
                time.sleep( .01 )
                assert( not healthy( file ) )
                time.sleep( 1 )
                file.dtr	= True
                time.sleep( .01 )
                health		= healthy( file )

        for index,group in accountgroups_input(
            cipher	= cipher,
            file	= file,
            encoding	= encoding,
            healthy	= healthy,
        ):
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
        if args.path:
            paths		= path_edit( paths, args.path )
        cryptopaths.append( (crypto,paths) )

    #
    # Set up serial device, if desired.  We will attempt to send each record using hardware flow
    # control (software XON/XOFF flow control is also possible, but requires a 2-way serial data
    # channel, which we want to avoid).  A record is considered to be successfully sent when
    #
    # 1. The counterparty assert DTR (Data Terminal Ready), which is connected to the local DSR (and
    #    maybe also DCD, which we ignore).  Only if DSR stays asserted for the entire duration of
    #    the transmission do we consider the record to have been received.  We will check it
    #    periodically (if possible), but at least at the beginning and end of the record's
    #    communication.  If not asserted, we will wait and retry the record -- and also re-send the
    #    nonce (assuming that the counterparty may have restarted).  An Exception will be raised
    #    if any of these failure conditions are detected during transmission of the record.
    #
    # 2. During communication of the record, we will only transmit data when the counterparty
    #    asserts RTS (Request To Send).  This is connected to our local CTS (Clear To Send).  The
    #    serial UART is configured to do this flow-control automatically.  We will block until CTS
    #    is asserted; this blockage may endure for very long periods of time; therefore, we will
    #    specify an infinite write_timeout.
    #
    file			= None
    encoding			= None
    healthy			= None
    file_opener			= None
    if args.device:
        # A write-only Serial connection, w/ hardware RTS/CTS and DTR/DSR flow control.
        encoding		= 'UTF-8'
        healthy			= serial_connected

        def file_opener():
            ser			= Serial(
                port	= args.device,
                baudrate = args.baudrate or BAUDRATE,
                xonxoff	= False,
                rtscts	= True,
                dsrdtr	= True,
                #write_timeout = 1/10,	# Re-inspect port every so often on blocked write; nope, block
            )
            ser.dtr		= False
            assert not healthy( ser )
            time.sleep( 1 )
            ser.dtr		= True
            return ser

    nonce_emit			= True
    for index,group in enumerate( accountgroups(
        master_secret	= secret,
        cryptopaths	= cryptopaths,
    )):
        if file is None and file_opener:
            file	= file_opener()
            log.warning( f"{file!r:.36} opened for output" )
            # Wait 'til counterparty responds to our DSR w/ their own DTR.
            while not ( health := file_outputline( file, "", encoding=encoding, healthy=healthy )):
                time.sleep( 1 )
                
        while not ( health := accountgroups_output(
            group	= group,
            index	= index if args.enumerated else None,
            cipher	= cipher,
            nonce	= nonce,
            file	= file,
            encoding	= encoding,
            corrupt	= float( args.corrupt ) if args.corrupt else 0,
            nonce_emit	= nonce_emit,
            healthy	= healthy
        )):
            # Output health failed during/after sending group.  We're going to start over.  Try to
            # re-open the target file every second or so.
            nonce_emit		= True
            if file is not None:
                file.close()
                log.warning( f"{file!r:.36} closed because it was detected as unhealthy" )
                file		= None
            time.sleep( 1 )

        # Output health confirmed during/after sending group; carry on.
        nonce_emit		= False

    return 0
