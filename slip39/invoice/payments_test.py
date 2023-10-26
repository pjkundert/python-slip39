import pytest
import logging
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
            #print( f"gen. yield: {n, vo}" )
            v,			= ( yield n, vo )
            #print( f"gen. recvd: {v}" )
            assert v == vo

    gi				= generator( 3 )
    try:
        credentials		= None
        while True:
            #print( f"iter send:  {credentials}" )
            n,vo		= gi.send( credentials )
            credentials		= None
            #print( f"iter next:  {n,vo}" )
            credentials		= (ordinal( n ),)
    except StopIteration:
        log.info( f"done w/ n == {n}, s == {vo}" )


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

    # os.symlink( name_ss + '.crypto-license', base_cl.with_suffix( '.crypto-license' ))

    # Get a Client Agent Keypair, to use to self-sign the License
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
    keyp_cl_raw			= keyp_cl.into_keypair( username=user_cl, password=pswd_cl )

    ls				= subprocess.run(
        [ 'ls', '-l', str( here ) ], stdout=subprocess.PIPE,
    )
    log.info( f"Test directory:\n{ls.stdout.decode( 'UTF-8' )}\n\n" )

    # The licensing.authorized API should now be able to issue this self-signed.crypto-license
    # on-demand, IF it can find a Keypair.  It will not find it by looking for
    # self-signed.crypto-license, b/c self-signed.crypto-keypair is encrypted with different
    # credentials.
    with pytest.raises( licensing.NotRegistered ) as excinfo:
        assert list( licensing.authorized(
            author	= author,
            basename	= str( base_ss ),
            confirm	= False,
            registering	= False,
            acquiring	= False,
        )) == [ (None,None) ]
    # But w/ a Keypair, we can get a self-signed License issued
    auth_str = licensing.into_JSON(
        [
            ( licensing.KeypairPlaintext( k ) if k else None, l )
            for k,l in licensing.authorized(
                author		= author,
                basename	= str( base_ss ),
                confirm		= False,
                registering	= False,
                acquiring	= False,
                keypairs	= [ keyp_cl_raw ],
            )
        ], indent=4, default=str,
    )
    print( auth_str )
    assert auth_str == """\
[
    [
        {
            "sk":"u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7t9WcViPdQKdKpNWjKsZF07P5Xa6uTCK+JUdt1qSG9zgg==",
            "vk":"fVnFYj3UCnSqTVoyrGRdOz+V2urkwiviVHbdakhvc4I="
        },
        {
            "license":{
                "author":{
                    "name":"fVnFYj3UCnSqTVoyrGRdOz+V2urkwiviVHbdakhvc4I=",
                    "pubkey":"fVnFYj3UCnSqTVoyrGRdOz+V2urkwiviVHbdakhvc4I="
                },
                "dependencies":[
                    {
                        "license":{
                            "author":{
                                "domain":"self-signed.com",
                                "name":"Dominion Research & Development Corp.",
                                "product":"Self Signed",
                                "pubkey":"5zTqbCtiV95yNV5HKqBaTEh+a0Y8Ap7TBt8vAbVja1g="
                            },
                            "grant":{
                                "self-signed":{
                                    "some-capability":10
                                }
                            }
                        },
                        "signature":"I/o9+bacFBOwTPgNfduUwdgldMRPVCQPUEN4h3yynqzv4sDyEe37oCslnB7gjM8VBojp3vdZbdlmO7HhxLJQDA=="
                    }
                ]
            },
            "signature":"/OWpu8M4HczWnTXwW5yPchZpdI7B/k7c2GtaiK++itlzm8UY2Gl0DMe2k4HDZY6cg6t1cPi3EgjjtZXrWuLACQ=="
        }
    ],
    [
        {
            "sk":"u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7t9WcViPdQKdKpNWjKsZF07P5Xa6uTCK+JUdt1qSG9zgg==",
            "vk":"fVnFYj3UCnSqTVoyrGRdOz+V2urkwiviVHbdakhvc4I="
        },
        null
    ]
]"""

    client			= licensing.Agent(
        name	= "Perry Kundert",
        service	= "client-user",
        pubkey	= keyp_cl['vk'],
    )
    log.info( f"Client: {client}" )

    # We'll be loading an existing Client Agent keypair, so restrict it from registering a new one.
    # We'll look for Licenses issued under the basenames of client.service (an already issued
    # sub-license), and author.service (eg. an author-issued License we can sub-license). If no
    # already issued License is found, tt must try to load the Author's License (using the
    # author.service as the basename), and then attempt to sign and save an instance of it with the
    # client Agent's Keypair.  For this, we need access to an Agent Keypair suitable for signing
    # (access to decrypted private key); so we'll need the credentials.
    machine_id_path		= test.with_suffix( '' ) / "payments_test.machine-id"
    reloader			= reload(
        author		= author,
        client		= client,
        registering	= False,
        reverse_save	= True,
        basename	= None,         # name_cl,  # basename of the License, and the Keypair use to self-sign it
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

    # Later, we restore from backup and our Machine ID changes...  This will cause a
    # LicenseSigned.verify failure.
    assert len( licenses ) == 1
    with pytest.raises( licensing.LicenseIncompatibility ) as excinfo:
        constraints		= licenses[0].verify(
            author_pubkey	= client.pubkey,
            confirm		= False,
        )
    assert "specifies Machine ID 00010203-0405-4607-8809-0a0b0c0d0e0f; found" in str( excinfo.value )
