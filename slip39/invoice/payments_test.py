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

    #test			= Path( __file__ ).resolve().parent,    # Our payments_test.crypto-keypair... file w/ O2o...2ik=
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
    log.warning( f"Author: {author}" )

    # Now create the License suitable for self-signing; no client (so any client can sign it)
    lic				= licensing.license(
        basename	= str( base_ss ),
        author		= author,
        grant		= {'self-signed': { 'some-capability': 10 }},
        confirm		= False,  # Not a real domain...
    )
    log.warning( f"Self-Signable License: {lic}" )

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
    log.warning( f"Test directory:\n{ls.stdout.decode( 'UTF-8' )}\n\n" )

    client			= licensing.Agent(
        name	= "Perry Kundert",
        service	= "client-user",
        pubkey	= keyp_cl['vk'],
    )
    log.warning( f"Client: {client}" )

    # We'll be loading an existing Client Agent keypair, so restrict it from registering a new one.
    # It must try to load the Author's License (using the author.service as the basename), and then
    # attempt to sign and save an instance of it with the client Keypair.
    reloader			= reload(
        author		= author,
        client		= client,
        registering	= False,
        reverse_save	= True,
        basename	= name_cl,  # basename of the License, and the Keypair use to self-sign it
        confirm		= False,
        extra		= [ str( here ) ],
    )

    username			= user_cl
    password			= pswd_cl
    try:
        key,val			= next( reloader )
        while True:
            log.warning( f"test_grants <-- {key}: {val}" )
            if key == Process.PROMPT:
                if 'username' in val:
                    log.warning( f"test_grants --> {username}" )
                    key,val	= reloader.send( username )
                    continue
                elif 'password' in val:
                    log.warning( f"test_grants --> {password}" )
                    key,val	= reloader.send( password )
                    continue
                else:
                    log.warning( f"test_grants -x- ignoring  {val}" )
            key,val		= next( reloader )
    except StopIteration:
        log.warning( f"test_grants xxx Done w/ key == {key}, val == {val}" )
