import codecs
import logging
import sys
import json
import random

from ..types		import Account
from ..util		import input_secure

log				= logging.getLogger( __package__ )


def nonce_add(
    nonce: bytes,
    offset: int,
):
    nonce_len			= len( nonce )
    nonce_int			= int.from_bytes( nonce, 'big' )
    nonce_now			= (( nonce_int + int( offset )) % 2**( 8 * nonce_len ))
    return nonce_now.to_bytes( nonce_len, 'big' )


def accountgroups_input(
    cipher	= None,			# Are input accountgroups records encrypted?
    file	= None,			# Where to retrieve input from
):
    """Receive and yield accountgroups, ignoring any that cannot be parsed.  Add the enumeration to the
    nonce for decrypting.

    The session nonce must be recovered from the first line of input.

    """
    nonce			= None
    while True:
        # TODO: detect EOF
        record			= input_secure( "Account '[<index>:] <group>' ({'encrypted' if cipher else 'plaintext'}): ", secret=False )
        index			= None
        try:
            if cipher:
                index,payload	= record.split( ':', 1 )
                if nonce is None:
                    log.info( f"Decoding encrypted nonce: {record!r}" )
                    try:
                        assert index.strip() == 'nonce', \
                            f"Failed to find 'nonce' enumeration prefix on first record: {record!r}"
                        ciphertext	= bytearray( codecs.decode( payload.strip(), 'hex_codec' ))
                        log.debug( "Found nonce: {ciphertext.hex}" )
                        nonce		= bytes( cipher.decrypt( b'\x00' * 12, ciphertext ))
                    except Exception as exc:
                        message		= f"Failed to recover nonce from {record!r}; cannot proceed: {exc}"
                        log.error( message )
                        return message
                    log.warning( f"Decrypting accountgroups with nonce: {nonce.hex()}" )
                    continue
                nonce_now	= nonce_add( nonce, int( index ))
                ciphertext	= bytearray( bytes.fromhex( payload ))
                plaintext 	= bytes( cipher.decrypt( nonce_now, ciphertext ))
                record		= plaintext.decode( 'UTF-8' )
            group		= json.loads( record )
        except Exception as exc:
            log.warning( f"Discarding invalid record {record:.20}: {exc!r}" )
            yield None, None
        else:
            yield index, group


def accountgroups_output(
    group,
    index	= None,		# If encrypting, None will emit encrypted nonce
    cipher	= None,
    nonce	= None,
    file	= None,
    flush	= True,
    corrupt	= 0,
):
    """Emit accountgroup records to the provided file, or sys.stdout.

    For each record, we will support either a sequence of Accounts (produced by accountgroups()), or
    a sequence of tuples of (<crypto>, <path>, <address>), (ie. recovered via accountgroups_input.

    """
    assert not cipher or ( nonce and index is not None ), \
        "Encryption requires both nonce and index"

    # For encrypted output, the first record emitted must be the encrypted nonce.
    if cipher and nonce and index == 0:
        # Emit the one-time record containing the encrypted nonce, itself w/ a zero nonce.
        plaintext		= bytearray( nonce )
        ciphertext		= bytes( cipher.encrypt( b'\x00' * len( nonce ), plaintext ))
        record			= ( 'nonce', ciphertext.hex(), )
        output			= ": ".join( record )
        log.info( f"Encrypting accountgroups with nonce: {nonce.hex()}" )
        print( output, file=file or sys.stdout, flush=flush )

    if not group:
        return		# Ignore un-parsable/empty groups

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
    print( output, file=file or sys.stdout, flush=flush )
