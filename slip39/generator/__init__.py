import codecs
import sys
import json
import random


def nonce_add(
    nonce: bytes,
    offset: int,
):
    nonce_len		= len( nonce )
    nonce_int		= int.from_bytes( nonce, 'big' )
    nonce_now		= (( nonce_int + int( offset )) % 2**( 8 * nonce_len ))
    return nonce_now.to_bytes( nonce_len, 'big' )


def accountgroups_output(
    group,
    index	= None,		# If encrypting, None will emit encrypted nonce
    cipher	= None,
    nonce	= None,
    file	= None,
    flush	= True,
    corrupt	= 0,
):
    assert not cipher or ( nonce and index is not None ), \
        "Encryption requires both nonce and index"
    # For encrypted output, the first record emitted must be the encrypted nonce.
    if cipher and nonce and index == 0:
        # Emit the one-time record containing the encrypted nonce, itself w/ a zero nonce.
        plaintext	= bytearray( nonce )
        ciphertext	= bytes( cipher.encrypt( b'\x00' * len( nonce ), plaintext ))
        record		= ( 'nonce', ciphertext.hex(), )
        output		= ": ".join( record )
        print( output, file=file or sys.stdout, flush=flush )

    # Emit the (optionally encrypted and indexed) record
    payload		= (json.dumps([
        (acct._cryptocurrency.SYMBOL, acct.path, acct.address)
        for acct in group
    ]))
    if cipher:
        plaintext	= bytearray( payload.encode( 'UTF-8' ))
        nonce_now	= nonce_add( nonce, index )
        ciphertext	= bytes( cipher.encrypt( nonce_now, plaintext ))
        record		= ( codecs.encode( ciphertext, 'hex_codec' ).decode( 'ascii' ), )
    else:
        record		= ( payload, )

    if index is not None:
        record		= ( f"{index:>5}", ) + record

    output		= ": ".join( record )
    if corrupt:
        fraction	= corrupt / 100
        output		= ''.join(
            random.choice( 'abcdefghijklmnopqrstuvwxyz0123456789' ) if random.random() < fraction else c
            for c in output
        )
    print( output, file=file or sys.stdout, flush=flush )
