import codecs
import hashlib
import logging
import sys
import json
import random

# Optionally, we can provide ChaCha20Poly1305 to support securing the channel.  Required if the
# --en/decrypt option is used.
try:
    from chacha20poly1305 import ChaCha20Poly1305
except ImportError:
    pass

from ..types		import Account

log				= logging.getLogger( __package__ )


def chacha20poly1305( password: str ) -> ChaCha20Poly1305:
    """Stretch the password (w/ sha256 without a salt!, not pbkdf2_hmac, as this must be easily
    replicable in the receiver who has only the password).  The security requirements of this
    channel is not high, because only public wallet addresses are being transported, so this is
    acceptable.  A one-time Nonce must be used whenever the same password is used, though.

    """
    key				= hashlib.sha256()
    key.update( password.encode( 'UTF-8' ))
    return ChaCha20Poly1305( key=key.digest() )


def nonce_add(
    nonce: bytes,
    offset: int,
):
    nonce_len			= len( nonce )
    nonce_int			= int.from_bytes( nonce, 'big' )
    nonce_now			= (( nonce_int + int( offset )) % 2**( 8 * nonce_len ))
    return nonce_now.to_bytes( nonce_len, 'big' )


def accountgroups_input(
    cipher	= None,		# Are input accountgroups records encrypted?
    file	= None,		# Where to retrieve input from
    encoding	= None,		# Does channel require decoding from binary? Use this encoding, if so
    healthy	= None,		# Is file healthy for reading?  Read and ignore input while not.
):
    """Receive and yield accountgroups, ignoring any that cannot be parsed, or received while not
    healthy.  Add the enumeration to the nonce for decrypting.

    The session nonce must be recovered from the first line of input.

    """
    if file is None:
        file			= sys.stdin
    nonce			= None
    while True:
        # Attempt to receive a record, while connection is healthy
        try:
            record		= None
            while not record or not record.endswith( b'\n' if type(record) is bytes else '\n' ):
                recv		= file.readline()
                health		= healthy is None or healthy( file )
                if not health:
                    if recv:
                        log.warning( f"{file!r:.32} Unhealthy; ignoring input: {recv!r}" )
                    break
                if recv:
                    if record is None:
                        record	= recv
                    else:
                        record += recv
        except EOFError:
            # Session has terminated; TODO: yield the EOFError to signal no more inputs (ever) available?
            return
        if not health:
            yield None,None
            continue

        # Got a record on a healthy connection!
        if encoding:  # Eg. if file is binary (eg. a Serial device), decode
            try:
                record		= record.decode( encoding )
            except Exception as exc:
                log.warning( f"Discarding invalid record {record!r}: {exc!r}" )
                yield None, None
                continue

        # Ignore empty records
        record			= record.strip()
        if not record:
            continue

        # See if records are indexed.  Only int or 'nonce' is accepted for index.
        index			= None
        try:
            index,payload	= record.split( ':', 1 )        # ValueError if not <index>:<payload>
            index		= int( index )			# ValueError if <index> not int
        except ValueError:
            if index != 'nonce':				# Otherwise, only 'nonce': <payload> acceptable
                index,payload	= None,record			# ...if not; then records are not indexed.

        try:
            if cipher:
                if nonce is None or index == 'nonce':
                    # Either this is the first record ever received, *or* the counterparty has
                    # restarted and/or is re-noncing the session.
                    try:
                        assert index == 'nonce', \
                            f"Failed to find 'nonce' enumeration prefix on first record: {record!r}"
                        ciphertext	= bytearray( codecs.decode( payload.strip(), 'hex_codec' ))
                        nonce		= bytes( cipher.decrypt( b'\x00' * 12, ciphertext ))
                    except Exception as exc:
                        message		= f"Failed to recover nonce from {record!r}; cannot proceed: {exc}"
                        log.error( message )
                        return message
                    log.info( f"Decrypting accountgroups with nonce: {nonce.hex()}" )
                    continue

                nonce_now	= nonce_add( nonce, index )
                ciphertext	= bytearray( bytes.fromhex( payload ))
                plaintext 	= bytes( cipher.decrypt( nonce_now, ciphertext ))
                payload		= plaintext.decode( 'UTF-8' )
            group		= json.loads( payload )
        except Exception as exc:
            log.warning( f"Discarding invalid record {record!r}: {exc!r}" )
            yield None, None
        else:
            yield int(index), group


def file_outputline(
    file,
    output,
    encoding	= None,
    flush	= True,
    healthy	= None,
):
    """Returns the health of the file at the end of the output write/flush.  Unhealthy file_output
    should return False, allowing the caller to re-try opening the channel and outputting the
    record.

    A predicate 'healthy' takes a file that tests for its health, returns True iff healhty, False or raising
    Exception if not healthy.

    """
    if file is None:
        file			= sys.stdout

    output		       += '\n'
    if encoding:
        output			= output.encode( encoding )

    # Confirm that the file is healthy before writing output
    if ( health := healthy is None or healthy( file )):
        log.info( f"File {file!r:.36} writing {len(output):3}: {output!r:.36}{'...' if len(output) >36 else ''}" )
        file.write( output )
    if not health:
        log.warning( f"File {file!r:.36} became unhealthy before output of {output!r}" )
        return health

    # Confirm that the file was healthy right up 'til the buffer is done flushing
    while ( health := healthy is None or healthy( file )) and flush:
        '''
        if flush and hasattr( file, 'out_waiting' ):
            if ( waiting := file.out_waiting ) > 0:
                log.info( f"{file!r:.32} waiting for {waiting} bytes to flush" )
                time.sleep( 1/100 )
                continue
            flush		= False
        elif flush:
            file.flush()
            flush		= False
        '''
        file.flush()
        flush			= False

    if not health:
        log.warning( f"File {file!r:.36} became unhealthy during output of {output!r}" )
    return health


def accountgroups_output(
    group,
    index	= None,
    cipher	= None,
    nonce	= None,
    file	= None,
    flush	= True,
    corrupt	= 0,
    nonce_emit	= True,		# force encrypted Nonce to be emitted
    encoding	= None,		# Does channel require encoding to binary? Use this encoding, if so
    healthy	= None,		# Detect health of file
):
    """Emit accountgroup records to the provided file, or sys.stdout.

    For each record, we will support either a sequence of Accounts (produced by accountgroups()), or
    a sequence of tuples of (<crypto>, <path>, <address>), (ie. recovered via accountgroups_input.

    Supports binary file-like objects (eg pyserial.Serial) w/ the encoding parameter.  Outputs one line,
    blocking forever -- the counterparty can (and likely will) block for an indeterminate amount of time,
    as it waits to use the provided account groups.

    Returns the health of the output before, during and after attempted output write/flush.

    """
    assert not cipher or ( nonce and index is not None ), \
        "Encryption requires both nonce and index"

    # For encrypted output, the first record emitted always must be the encrypted nonce.  This might
    # occur multiple times outputting a stream of data, if it is detected that the counterparty has
    # restarted.  Serial port pins such as DTR/DSR can be used to detect counterparty disconnection.
    # Always emit extra leading newlines to restart the counterparty line reading, since we don't
    # know what kind of input remains in its buffer.
    if cipher and nonce and nonce_emit:
        # Emit the one-time record containing the encrypted nonce, itself w/ a zero nonce.
        plaintext		= bytearray( nonce )
        ciphertext		= bytes( cipher.encrypt( b'\x00' * len( nonce ), plaintext ))
        record			= ( 'nonce', ciphertext.hex(), )
        output			= "\n\n" + ": ".join( record )
        log.info( f"Encrypting accountgroups with nonce: {nonce.hex()}" )
        if not file_outputline( file, output, encoding=encoding, flush=flush, healthy=healthy ):
            return False

    if not group or ( cipher and index is None ):
        return		# Ignore un-parsable/empty groups, or encrypting w/ no index

    # Emit the (optionally encrypted and indexed) accountgroup record.
    payload			= json.dumps([
        (acct.crypto, acct.path, acct.address) if isinstance( acct, Account ) else acct
        for acct in group
    ])
    if cipher:
        plaintext		= bytearray( payload.encode( 'UTF-8' ))
        nonce_now		= nonce_add( nonce, index )
        ciphertext		= bytes( cipher.encrypt( nonce_now, plaintext ))
        record			= ( codecs.encode( ciphertext, 'hex_codec' ).decode( 'ascii' ), )
    else:
        record			= ( payload, )

    if index is not None:
        record			= ( f"{index:>5}", ) + record

    output			= ": ".join( record )
    if corrupt:
        fraction		= corrupt / 100
        output			= ''.join(
            random.choice( 'abcdefghijklmnopqrstuvwxyz0123456789' ) if random.random() < fraction else c
            for c in output
        )

    # Finally, output the record, returning the health of the file at the end of the transmission
    return file_outputline( file, output, encoding=encoding, flush=flush, healthy=healthy )
