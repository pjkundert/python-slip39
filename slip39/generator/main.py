
#
# Python-slip39 -- Ethereum SLIP-39 Account Generation and Recovery
#
# Copyright (c) 2022, Dominion Research & Development Corp.
#
# Python-slip39 is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is also available under alternative (eg. Commercial) licenses, at
# your option.  See the LICENSE file at the top of the source tree.
#
# Python-slip39 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#

from __future__         import annotations

import argparse
import logging
import time

from collections	import namedtuple

from serial		import Serial

from .			import chacha20poly1305, accountgroups_output, accountgroups_input
from ..util		import log_cfg, log_level, input_secure
from ..defaults		import BAUDRATE, CRYPTO_PATHS
from ..			import Account, cryptopaths_parser
from ..api		import accountgroups, random_secret

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( __package__ )

DtrDsr				= namedtuple( 'DtrDsr', ('dtr', 'dsr') )
RtsCts				= namedtuple( 'RtsCts', ('rts', 'cts') )


def serial_flow( ser ):
    dtrdsr			= DtrDsr(
        dtr	= ser.dtr,		# Do we output an asserted DTR?
        dsr	= ser.dsr,		# ...and what is our current input DSR (our counterparty's DTR)?
    )
    rtscts			= RtsCts(
        rts	= ser.rts,		# Do we output RTS an asserted?
        cts	= ser.cts,		# ...and what is our current CTS (our counterparty's RTS)?
    )
    return dtrdsr,rtscts


def serial_status( dtrdsr, rtscts ):
    return ( f"DTR --> {'1' if dtrdsr.dtr else 'x'} / DSR <-- {'1' if dtrdsr.dsr else 'x'},"
             + f" RTS --> {'1' if rtscts.rts else 'x'} / CTS <-- {'1' if rtscts.cts else 'x'}"
             + ( "" if rtscts.cts else "; Receiver full " )
             + ( "" if dtrdsr.dtr else "; Receiver not connected " ))


def serial_connected( ser ):
    """Detect if the serial port is connected by monitoring DSR/DTR. """
    dtrdsr,rtscts		= serial_flow( ser )
    health			= dtrdsr.dsr and dtrdsr.dtr
    if health:
        log.info( f"{ser!r:.36}: {serial_status( dtrdsr, rtscts )}; Healthy" )
    else:
        log.warning( f"{ser!r:.36}: {serial_status( dtrdsr, rtscts )}; Unhealthy; missing DSR and/or DTR" )
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
                     help=f"Specify crypto address formats: {', '.join( Account.FORMATS )}; default: " + ', '.join(
                         f"{c}:{Account.address_format(c)}" for c in Account.CRYPTO_NAMES.values()
                     ))
    ap.add_argument( '--xpub', default=False, action='store_true',
                     help="Output xpub... instead of cryptocurrency wallet address (and trim non-hardened default path segments)" )
    ap.add_argument( '--no-xpub', dest='xpub', action='store_false', help="Inhibit output of xpub (compatible w/ pre-v10.0.0)" )
    ap.add_argument( '-c', '--cryptocurrency', action='append',
                     default=[],
                     help="A crypto name and optional derivation path (default: \"ETH:{Account.path_default('ETH')}\"), optionally w/ ranges, eg: ETH:../0/-" )
    ap.add_argument( '--path',
                     default=None,
                     help="Modify all derivation paths by replacing the final segment(s) w/ the supplied range(s), eg. '.../1/-' means .../1/[0,...)")
    ap.add_argument( '-d', '--device', type=str,
                     default=None,
                     help="Use this serial device to transmit (or --receive) records" )
    ap.add_argument( '--baudrate', type=int,
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
    log.debug( f"args: {args!r}" )
    assert not args.encrypt or args.enumerate, \
        "When --encrypt is specified, --enumerated is required"
    assert not args.receive or not ( args.path or args.secret ), \
        "When --receive, no --path nor --secret allowed"
    if args.path:
        assert args.path.startswith( 'm/' ) or ( args.path.startswith( '..' ) and args.path.lstrip( '.' ).startswith( '/' )), \
            "A --path must start with 'm/', or '../', indicating intent to replace 1 or more trailing components of each cryptocurrency's derivation path"

    # If any --format <crypto>:<format> address formats provided.  If not represented in
    # --cryptocurrency, add it; specifying a format implies interest in that cryptocurrency.
    if not args.cryptocurrency:
        args.cryptocurrency	= list( CRYPTO_PATHS )  # the defaults, if none provided
    for cf in args.format:
        try:
            crypto,format	= cf.split( ':' )
            Account.address_format( crypto, format=format )  # Changes the default for crypto
            if not any( k.startswith( crypto ) for k in args.cryptocurrency ):
                args.cryptocurrency.append( crypto )
        except Exception as exc:
            log.error( f"Invalid address format: {cf}: {exc}" )
            raise

    # Master secret seed supplied as hex, x{pub,prv}..., BIP-39/SLIP-39 Mnemonic(s)
    master_secret		= None
    if not args.receive:
        master_secret		= args.secret or '-'
        if master_secret == '-':
            master_secret	= input_secure( 'Master secret hex/xpub/mnemonic: ', secret=True )
        else:
            log.warning( "It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input" )

    # Create cipher if necessary.  The nonce must only be used for one message; we'll increment it
    # below by the index of each record we send.  It must only be transmitted once; a fresh nonce
    # will be generated for each serial session.
    cipher,nonce		= None,None
    encrypt			= args.encrypt
    if encrypt == '-':
        encrypt			= input_secure( 'Encryption password: ', secret=True )
    if encrypt:
        cipher			= chacha20poly1305( password=encrypt )

    receive_latency		= 1/10
    if args.receive:
        # Receive groups, ignoring any that cannot be parsed.
        file			= None
        encoding		= None
        healthy			= None
        healthy_reset		= None
        file_opener		= None
        if args.device:
            # Await the appearance of a healthy connection to a live (DTR-asserting) peer.
            healthy		= serial_connected
            encoding		= 'UTF-8'

            def file_opener():  # noqa: F811
                ser		= Serial(
                    port	= args.device,
                    baudrate	= args.baudrate or BAUDRATE,
                    xonxoff	= False,
                    rtscts	= True,
                    dsrdtr	= False,			# We will monitor DSR and control DTR manually; it starts low
                    timeout	= receive_latency,		# Re-inspect port every so often on incomplete reads
                )
                return ser

            def healthy_reset( file ):  # noqa: F811
                file.dtr		= False
                # Wait for a server to de-assert DTR, discarding input.  After the Server has de-asserted, we still need to drain
                # the Server's output / Client's input buffers, so keep flushing 'til input buffer empty...
                read			= None
                while ( flow := serial_flow( file ) ) and ( flow[0].dsr or read ):
                    log.warning( f"{file!r:.36} {serial_status(*flow)}; Client lowered DTR -- awaiting Server reset" )
                    read		= file.readline()       # could block for timeout
                    if read:
                        log.warning( f"{file!r:.36} {serial_status(*flow)}; Discarded {len(read)} input: {read!r:.32}{'...' if len(read) > 32 else ''}{read[-3:]!r}" )

                # Server done sending after it has reset its DTR.  Initiate Client ready!
                file.dtr		= True

                # Server has reset; Client has run it out of output/input, and asserted DTR; discard
                # input 'til Server asserts DTR; will always send a few newlines after reset.
                while ( flow := serial_flow( file ) ) and not flow[0].dsr:
                    log.warning( f"{file!r:.36} {serial_status(*flow)}; Client asserts DTR -- awaiting Server active" )
                    read		= file.readline()       # could block for timeout
                    if read:
                        log.warning( f"{file!r:.36} {serial_status(*flow)}; Discarded {len(read)} input: {read!r:.32}{'...' if len(read) > 32 else ''}{read[-3:]!r}" )

        # Continually attempt to receive records.  If a file_opener is provided, we'll continue
        # indefinitely (eg. a Serial connection, which may present multiple connections and
        # disconnections.)  However, the default (sys.stdin) only continues 'til the first EOF.
        first			= True
        while first or file_opener:
            first		= False

            # (Re-)establish a session, if None established and a file_opener is provided.
            if file is None and file_opener:
                file		= file_opener()
            if healthy_reset:
                healthy_reset( file )

            # Receive each group, or None,None indicating no record parsed, either due to decryption
            # failure (eg. bad record), or due to connection health.  Will quit if a server session
            # doesn't produce a nonce as its first record.
            for index,group in accountgroups_input(
                cipher		= cipher,
                file		= file,
                encoding	= encoding,
                healthy		= healthy,
            ):
                if index is not None and group:
                    accountgroups_output( group, index=index )
                    continue
                if healthy and healthy( file ):
                    continue
                # Bad connection, awaiting health...
                if healthy_reset:
                    healthy_reset( file )

            # The connection has terminated for some reason (eg. no nonce).  Try again.
            file		= None

        return 0

    # ...else...
    # Transmitting.

    # What cryptocurrency addresses are requested?  If --xpub, then for those with "default" paths,
    # trim off the non-hardened components.  In other words, if
    #
    #     --crypto BTC
    #
    # is specified, emit BTC "bc1..." bech32 addresses at m/84'/0'/0'/0/0, m/84'/0'/0'/0/1, ...
    #
    # However, if
    #
    #     --xpub --crypto BTC
    #
    # is specified, emit BTC "zpub..." xpubkeys at m/84'/0'/0', m/84'/0'/1', ...
    cryptopaths			= list( cryptopaths_parser(
        args.cryptocurrency,
        edit			= args.path,
        hardened_defaults	= args.xpub,
    ))

    #
    # Set up serial device, if desired.  We will attempt to send each record using hardware flow
    # control (software XON/XOFF flow control is also possible, but requires a 2-way serial data
    # channel, which we want to avoid).
    #
    # The channel is opened by following procedure:
    #
    # 0. The Server (sender) starts with its DTR low, and prepares to send its new nonce.
    #
    # 1. The Client (receiver) sees the Server's (sender's) DTR is low by seeing a low DSR.  All
    #    input is discarded by the receiver.  The client responds by raising its DTR.
    #
    # 2. The Server (sender) sees its DSR asserted by the (new) client's DTR, and raises their DTR
    #    in response.  It then initiates communications by sending the initial nonce.
    #
    # The channel is closed by the client (ie. if it does not successfully receive a nonce within a
    # few seconds):
    #
    # 3c. The Client lowers its DTR.  It then goes to step 1., where consuming all input will
    #     eventually cause the Server to notice the loss of its DSR, and stop, lowering its DTR.
    #
    # The channel is closed by the server (ie. if it finishes sending the desired records, fails or
    # reboots):
    #
    # 3s. The Server lowers its DTR.  The client sees its low DSR, and goes to step 1.
    #
    # A record is considered to be successfully sent by the Server when:
    #
    # 1. The counterparty receiver asserts DTR (Data Terminal Ready), which is connected to the
    #    local DSR (and maybe also DCD, which we ignore).  Only if DSR stays asserted for the entire
    #    duration of the transmission do we consider the record to have been successfully received.
    #    We will check it periodically (if possible), but at least at the beginning and end of the
    #    record's communication.  If its RTS is not asserted, the Server will will wait in stop
    #    0. to re-send the record -- and also re-send the nonce (assuming that the counterparty may
    #    have restarted).
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
    healthy_waiter		= None
    file_opener			= None
    if args.device:
        # A write-only Serial connection, w/ hardware RTS/CTS and DTR/DSR flow control.
        encoding		= 'UTF-8'
        healthy			= serial_connected

        def file_opener():  # noqa: F811
            ser			= Serial(
                port	= args.device,
                baudrate = args.baudrate or BAUDRATE,
                xonxoff	= False,
                rtscts	= True,
                dsrdtr	= False,		# We will monitor DSR and control DTR manually; it starts low
            )
            return ser

        def healthy_waiter( file ):  # noqa: F811
            file.dtr		= False
            # Wait for a client; when seen, assert DTR
            while ( flow := serial_flow( file ) ) and not flow[0].dsr:
                log.warning( f"{file!r:.36} {serial_status(*flow)}; Server opened for output; awaiting Client" )
                time.sleep( 1 )
            file.dtr		= True
            # Give the client time to notice, by emitting some newlines over a duration longer than
            # the receive latency.
            for _ in range( 3 ):
                file.write( b'\n' )
                time.sleep( receive_latency )

    nonce_emit			= True
    nonce			= random_secret( 12 )

    for index,group in enumerate( accountgroups(
        master_secret	= master_secret,
        cryptopaths	= cryptopaths,
    )):
        if file is None and file_opener:
            file		= file_opener()
            if healthy_waiter:
                healthy_waiter( file )

        while not accountgroups_output(
            group	= group,
            xpub	= args.xpub,
            index	= index if args.enumerated else None,
            cipher	= cipher,
            nonce	= nonce,
            file	= file,
            encoding	= encoding,
            corrupt	= float( args.corrupt ) if args.corrupt else 0,
            nonce_emit	= nonce_emit,
            healthy	= healthy
        ):
            nonce_emit		= True
            nonce		= random_secret( 12 )
            if healthy_waiter:
                healthy_waiter( file )

        # Output health confirmed during/after sending group; carry on.
        nonce_emit		= False

    return 0
