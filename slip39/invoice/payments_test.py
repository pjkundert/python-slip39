import pytest
import logging
import os
import subprocess

from pathlib		import Path


from crypto_licensing	import licensing


from ..util		import ordinal
from .payments		import Process, reload

log				= logging.getLogger( "payments_test" )


def test_sending():
    """Test the transmission and receipt of data via iterator.send(...)"""
    def generator( count ):
        for n in range( count ):
            vo			= ordinal( n )
            print( f"gen. yield: {n, vo}" )
            v,			= ( yield n, vo )
            print( f"gen. recvd: {v}" )
            assert v == vo

    gi				= generator( 3 )
    try:
        credentials		= None
        while True:
            print( f"iter send:  {credentials}" )
            n,vo		= gi.send( credentials )
            credentials		= None
            print( f"iter next:  {n,vo}" )
            credentials		= (ordinal( n ),)
    except StopIteration:
        print( f"done w/ n == {n}, s == {vo}" )


def test_grants( tmp_path ):
    """Test self-signed Licensing.  This allows a Vendor to ship a "minimal" set of capabilities, for
    which the Client can pay, and issue a self-signed License to use.

    Of course, since it is self-signed, any Thief knowledgeable in the state of the art can issue
    themselves a License *without* paying!  So, don't use this method to ship highly valuable
    capabilities.

    Of course, any Thief knowledgeable in the state of the art can simply *remove* your License
    checking, and run the software anyway...

    """

    test			= Path( __file__ ).resolve()		# Our payments_test.py file
    here			= Path( tmp_path ).resolve()		# Our testing directory.

    name_ss			= "self-signed"
    base_ss			= here / name_ss
    seed_ss			= licensing.into_bytes( "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" )
    user_ss			= "sales@self-signed.com"
    pswd_ss			= "password"
    keyp_ss			= licensing.registered(
        basename	= str( base_ss ),
        seed		= seed_ss,
        username	= user_ss,
        password	= pswd_ss,
    )
    assert keyp_ss['vk'] == "5zTqbCtiV95yNV5HKqBaTEh+a0Y8Ap7TBt8vAbVja1g="

    author			= licensing.Agent(
        name		= licensing.COMPANY,
        domain		= "self-signed.com",
        product		= "Self Signed",
        keypair		= keyp_ss.into_keypair( username=user_ss, password=pswd_ss ),
    )
    log.info( f"Author: {author}" )

    # Now create the License suitable for self-signing; no client (so any client can sign it)
    lic				= licensing.license(
        basename	= str( base_ss ),
        author		= author,
        grant		= {'self-signed': { 'some-capability': 10 }},
        confirm		= False,  # Not a real domain...
    )
    log.info( f"Self-Signable License: {lic}" )

    # We've got a self-signed.crypto-license, signed by the Vendor, with no specific Client
    # specified.  It's good for anyone to use.  Lets make a link to it, under the name that our
    # client will use.

    name_cl			= "client-user"
    base_cl			= here / name_cl

    os.symlink( name_ss + '.crypto-license', base_cl.with_suffix( '.crypto-license' ))

    # Get a Client Agent, to use to self-sign the License
    seed_cl			= licensing.into_bytes( "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" )
    user_cl			= "end-user@client.com"
    pswd_cl			= "password"
    keyp_cl			= licensing.registered(
        basename	= str( base_cl ),
        seed		= seed_cl,
        username	= user_cl,
        password	= pswd_cl,
    )
    assert keyp_cl['vk'] == "fVnFYj3UCnSqTVoyrGRdOz+V2urkwiviVHbdakhvc4I="

    ls				= subprocess.run(
        [ 'ls', '-l', str( here ) ], stdout=subprocess.PIPE,
    )
    log.info( f"Test directory:\n{ls.stdout.decode( 'UTF-8' )}\n\n" )

    client			= licensing.Agent(
        name	= "Perry Kundert",
        service	= "client-user",
        pubkey	= keyp_cl['vk'],
    )
    log.info( f"Client: {client}" )

    # We'll be loading an existing Client Agent keypair, so restrict it from registering a new one.
    # It must try to load the Author's License (using the author.service as the basename), and then
    # attempt to sign and save an instance of it with the client Keypair.  For this, we need access
    # to an Agent Keypair suitable for signing (access to decrypted private key); so we'll need the
    # credentials.
    machine_id_path		= test.with_suffix( '' ) / "payments_test.machine-id"
    reloader			= reload(
        author		= author,
        client		= client,
        registering	= False,
        reverse_save	= True,
        basename	= name_cl,  # basename of the License, and the Keypair use to self-sign it
        confirm		= False,
        extra		= [ str( here ) ],
        constraints	= dict(
            machine	= True,
        ),
        machine_id_path	= machine_id_path,
    )

    username			= user_cl
    password			= pswd_cl
    grants			= None
    keypairs,licenses		= [],[]
    try:
        key,val			= next( reloader )
        while True:
            log.info( f"test_grants <-- {key}: {val}" )
            if key == Process.PROMPT:
                if 'username' in val:
                    log.info( f"test_grants --> {username}" )
                    key,val	= reloader.send( username )
                    continue
                elif 'password' in val:
                    log.info( f"test_grants --> {password}" )
                    key,val	= reloader.send( password )
                    continue
                else:
                    log.info( f"test_grants -x- ignoring  {val}" )
            elif key is Process.GRANTS:
                log.warning( f"Grants:  {val}" )
                grants		= val
            elif key is Process.KEYPAIR:
                log.warning( f"Keypair: {val}" )
                keypairs.append( val )
            elif key is Process.LICENSE:
                log.warning( f"License: {val[1]}, w/ Keypair: {licensing.KeypairPlaintext( val[0] )}" )
                keypairs.append( val[0] )
                licenses.append( val[1] )
            key,val		= next( reloader )
    except StopIteration:
        log.info( f"test_grants xxx Done w/ key == {key}, val == {val}" )

    assert str( grants ) == """\
{
    "self-signed":{
        "some-capability":10
    }
}"""
    # TODO: confirm appropriate payment before issuing self-signed license.

    # Now that we've got the self-signed License from Author, self-signed by Client, we can verify
    # the authenticity of the License without access to the private keys; only the public keys.
    ls				= subprocess.run(
        [ 'ls', '-l', str( here ) ], stdout=subprocess.PIPE,
    )
    log.info( f"Test directory (post self-signed issuance):\n{ls.stdout.decode( 'UTF-8' )}\n\n" )

    assert len( licenses ) == 1
    constraints			= licenses[0].verify(
        author_pubkey	= client.pubkey,
        confirm		= False,
        machine_id_path	= machine_id_path,
    )
    log.info( f"Verified self-signed License:\n{constraints}\n\n" )
    assert not constraints

    # Later, we restore from backup and our Machine ID changes...
    assert len( licenses ) == 1
    with pytest.raises( licensing.LicenseIncompatibility ) as excinfo:
        constraints			= licenses[0].verify(
            author_pubkey	= client.pubkey,
            confirm		= False,
        )
    assert "specifies Machine ID 00010203-0405-4607-8809-0a0b0c0d0e0f; found" in str( excinfo.value )
