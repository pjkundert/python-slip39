
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
from __future__          import annotations

import logging
import traceback
import sys

from typing		import Optional
from pathlib		import Path
from enum		import Enum

import crypto_licensing
from crypto_licensing	import licensing
from crypto_licensing.misc import deduce_name


"""
Invoice payments:

    Receiving payments for an invoice requires a round-trip with the vendor, to inform them of the
unique 'seed' assigned to the client.  Unless this data is *guaranteed* to have been delivered to
the vendor, they will never be able to process the received payment, even if the client pays the
generated account.

    Also, to guarantee that the vendor has authorized the licensing

    Therefore, the flow is:

1) Generate an Ed25519 Agent keypair for the client (or load an existing one).

   Useful for signing data available now, with future guarantee that it was indeed the keyholder
   that validated the data at the time.  For example, confirming a Cryptocurrency payment online and
   therefore issuing a "license" signed by the agent.  Later, when offline, the license can be
   loaded, and it can be confirmed that it was considered "valid" by the owner of the Ed25519
   private key (which may now be encrypted or otherwise unavailable), using only the local Agent's
   public key.

   Also useful for generating data (via Diffie-Hellman (D-H) "exchange") that is unique to an
   Client Agent and another party (eg. a Vendor), without communication (so long as each party knows
   the other party's public key).  Thus, with *only* communication of the parties public keys, both
   the Client and the Vendor can agree on some seed data.

2) Generate a unique data for the client.

   Once a level of "security" is agreed upon (see below), the seed data can be produced -- either by
   the Vendor (in a traditional client on-boarding flow, eg. Client # 12345), OR by the Client (by
   generating seed data and allocating it uniquely to the Client (and somehow informing the Vendor,
   so they can receive the payment).

    - Use the Client Agent's private key + Vendor Agent's public key to derive unique D-H secret.
    - Hash with whatever other local date (eg. Machine-ID, account User Name, ...) is required/desired

   With this seed data, we can now proceed to generating payment information.

   - This will be some combination of unique identifying material, associated or signed by Agent privkey

     - Machine ID; unique to one machine; changes on recovery from backup to a new machine
       - It is often a MAC address.  Probably too brittle; want to support recover from backup.

     - User Name; will remain constant across multiple machines, recovery from backups
       - Valid for any user who obtains the Agent keypair, and runs the software under the same user name
       - Valid when software + configuration is copied to any machine w/ the same account user name
       - Probably ok in most cases to allow multiple installations w/ same account user name

     - Just the Agent pubkey
       - Valid for anyone copying the configuration.  Probably too weak.

     - A Diffie-Hellman (D-H) from secrets sk1/2, ie. curve25519(sk1, curve25519(sk2)) == curve25519(sk2, curve25519(sk1))
       - Valid for (derivable by) anyone who holds the Agent keypair, and knows the Vendor public key

3) Send Agent's seed data to Vendor; receive something, eg. "data-signature", ...

   The Client-generated seed data (or the means to derive it) must be communicated to the Vendor, OR
   the Vendor must respond back to the Client with Vendor-generated seed data.

   It is optional to receive response data from the Vendor; usually, a one-way Client -> Vendor data
   flow is adequate.

   However, if a license signed by the Vendor is required (eg. to avoid software modification
   attacks, where the Client subverts the software to generate licenses, eg. in the absence of
   payment, then a response containing the signed license is possible.  However, it doesn't really
   improve the situation -- the client software can simply be subverted to avoid verifying the
   license.

   The normal situation would be to send a DKIM signed email to the Vendor w/ a Subject: line
   containing the seed data, and receive an auto-response eg. containing a verification code.  Since
   the client software originally generated the data (but didn't disclose it to the Agent's human
   author!), the client software itself can generate the DKIM-signed email w/ a Subject: line
   containing the required authentication code, and then await the Agent's author receiving and
   entering the correct code (Ideally, Reed-Solomon error coded to correct substitution/erasure
   errors common to human-transcribed data).

   - Send Client-generated data to the Vendor

     - Write it to the blockchain, eg. w/ MultiPayoutERC20.forwarder/forwarder_allocate
       - A 256-bit arbitrary data is associated w/ a _salt

     - Send DKIM-signed Email via ..communications.send_message w/ a Subject containing the data
       - The response' Subject may contain Vendor-generated data, eg. signature, challenge/response code

   - Receive Vendor-generated data

     - Via a standard Vendor's Client on-boarding flow
       - Client enter address, Vendor assigns and emails seed data

     - In response to a spontaneous DKIM-signed Email from the Client
       - Client sends email, optionally w/ some data (eg. public key), Vendor assigns/email data

   - Obtain vendor pubkey via DKIM from the Vendor's DNS
       - The  "data-signature" + "data" can be verified w/ the Vendor's pubkey

   - Use the "data-signature" 1st 256 bits (32 bytes) as the seed, store 2nd 32 bytes as its data?

     - This stores the entire signature in the MultiPayoutERC20 contract, proving that...

   - Verified "data" + "data-signature" + observation of payment (on blockchain)

4) Generate Client-unique Cryptocurrency address(es) and Invoice

   Now, the Client's software has sufficient seed data to generate the client-unique addresses.
   These could simply be generated from an xpub... key, at a HD Wallet derivation path derived from
   the seed data.  Or, they could use the seed data as the "salt" in an Ethereum CREATE2 contract
   address calculation, to generate single-purpose forwarding addresses.

   Either way, once the Ethereum, Bitcoin, ... addresses are generated, the Invoice can be generated
   for the desired functionality line-items, for whatever Fiat or Crypto price, payable in various
   Cryptocurrencies to the designated addresses.


5) Detect payment to the addresses

   Consult the blockchain (directly via a local node, or indirectly using one of the available
   public blockchain transaction services such as Alchemy or Infura, or monitoring services such as
   Etherscan, etc.  See .ethereum.* for various APIs for ETH and EEC-20 Tokens.

"""
log				= logging.getLogger( "payments" )


class Process( Enum ):
    FAILED	= 0		# Failed to process; val is the failure text
    PROMPT	= 1		# Some user input required; val is the prompt text
    KEYPAIR	= 2		# A Keypair, but no associated License(s); val is (Keypair,None)
    LICENSE	= 3		# Some Keypair/License; val is (Keypair,License)
    GRANTS	= 4		# Some License grants; val is the Grants


def reload(
    author: licensing.Agent,			# Details of the author's product we're licensing
    client: Optional[licensing.Agent] = None,   # ..and the intended specific client Agent
    username: Optional[str]	= None,		# The credentials for our client Agent's Keypair
    password: Optional[str]	= None,
    basename			= None,
    registering			= None,
    acquiring			= None,
    **kwds
):
    """Attempts to reload any existing client Agent Keypairs, and any License(s) authored to that
    client, and yields any (Process.GRANT, <Grants>) found.  If Keypair(s) are found, they will be
    yield (Process.KEYPAIR, <Keypair>).

    During the process, may yield 0 or more (Process.PROMPT, <str>) requesting input from the
    caller, which may be supplied via <generator>.send( ... ).

    If an error occurs (such as no Grants found), a (Process.ERROR, <str>) will be produced.  This
    will often be

    """
    # If no username/password provided, we'll loop once w/ None, then request input for subsequent authorizations
    cl_username			= '-' if username is None else username
    if cl_username == '-':
        username		= None
    cl_password			= '-' if password is None else password
    if cl_password == '-':
        password	        = None
    userpass_input		= cl_username == '-' or cl_password == '-'

    try:
        authorizations		= licensing.authorized(
            author	= author,
            client	= client,
            username	= username,
            password	= password,
            basename	= basename,
            registering	= registering,          # Issue an Agent ID if none found?
            acquiring	= acquiring,		# Acquire a License if none found?
            **kwds
        )

        loaded			= []
        try:
            # Iterate using authorizations.send(...) instead of next; if nothing to send, leave 'send' None
            credentials		= None
            while True:
                key,lic		= authorizations.send( credentials )
                log.detail( f"Reloading key: {key}, lic: {lic}" )
                credentials	= None
                if key is None or lic is None:
                    if key is not None:
                        # Found a Keypair (but no License); yield it
                        yield Process.KEYPAIR, key
                        continue

                    # Neither Keypair nor License; authorized has indicated it is out of options and
                    # is about to give up: unless we provide new credentials.
                    what		= "No License found for Agent ID {}".format(
                        licensing.into_b64( key.vk )) if key else "(No Agent ID Keypair found)"
                    if userpass_input:
                        what       += "; enter credentials"
                        if password != "-":
                            what   += " (leave blank to register w/ {}: {}".format(
                                username or "(no username)", '*' * len( password or '' ) or "(no password)" )
                    log.warning( what )
                    if not userpass_input:
                        continue
                    # No Agent ID/License loaded; username/password may be incorrect.  If none provided,
                    # then authorization may go on to register w/ the last-entered username/password.
                    # Either username or password may be updated, if desired.  Usually, credential input
                    # forces you to re-enter something you know to be correct; this loop does not.
                    # Failing to enter both credentials indicates satisfaction -- goes on to register a
                    # new Agent ID w/ credentials, if so.
                    userpass_updated = False
                    if cl_username == '-':
                        log.warning( "Asking for username..." )
                        username_update	= (
                            yield Process.PROMPT, "Enter {} username (leave empty for no change): ".format(
                                deduce_name( basename=basename, filename=kwds.get( 'filename' ), package=kwds.get( 'package' ),
                                             default=client and client.servicekey or "the" ))
                        )
                        userpass_updated |= bool( username_update )
                        if username_update:
                            username	= username_update
                    if cl_password == '-':
                        log.warning( "Asking for password..." )
                        password_update	= (
                            yield Process.PROMPT, "Enter {} password (leave empty for no change): ".format(
                                deduce_name( basename=basename, filename=kwds.get( 'filename' ), package=kwds.get( 'package' ),
                                             default=client and client.servicekey or "the" ))
                        )
                        userpass_updated |= bool( password_update )
                        if password_update:
                            password	= password_update
                    if userpass_updated:
                        log.detail( "Supplying new credentials for {}: {}".format(
                            username or "(no username)", '*' * len( password or '' ) or "(no password)" ))
                        credentials	= (username,password)
                        continue
                    log.detail( "No new credential(s) for {}: {}{}".format(
                        username or "(no username)", '*' * len( password or '' ) or "(no password)",
                        " (attempting to register new Agent ID)" if registering else " (authorization failed)" ))
                    # No Keypair (or perhaps a Keypair, but no License) found; no new credentials
                else:
                    # Found a Keypair and License; remember/yield it
                    loaded.append( (key,lic) )
                    yield Process.LICENSE, (key,lic)

        except StopIteration:
            log.detail( f"Completed licensing.authorized w/ {len(loaded)} Keypair/Licenses found" )

        assert loaded, \
            "Unable to find {}'s product {!r} service key {!r}; no Licenses found".format(
                author.name, author.product, author.servicekey )

        # Collect up all the License grants; there may be more than one, if the user has purchased
        # multiple Licenses at different times.  Ensures we only include a specific License once.
        grants			= licensing.Grant()
        once			= set()
        for key,lic in loaded:
            grants_lic		= lic.grants( once=once )
            log.normal( "Located Agent Ed25519 Keypair {pubkey} w/ {product} License (from {_from}){extra}".format(
                pubkey	= licensing.into_b64( key.vk ),
                product	= lic and lic.license.author.product or "End-User",
                _from	= "from {}".format( lic._from ) if lic._from else "locally issued",
                extra	= (( " w/ grants: {}".format( grants_lic ) if log.isEnabledFor( logging.DEBUG ) else "" )
                           + ( " merging w/ grants: {}".format( grants ) if log.isEnabledFor( logging.TRACE ) else "" )),
            ))
            grants	       |= grants_lic

        # And, finally: ascertain whether we've collected a Grant to run the Author's product
        assert author.servicekey in grants, \
            "Unable to find {}'s product {!r} service key {!r} in License Grants {}".format(
                author.name, author.product, author.servicekey, grants )

    except Exception as exc:
        log.error( "Failed loading Agent Keypair and/or License: {exc}".format(
            exc=''.join( traceback.format_exception( *sys.exc_info() )) if log.isEnabledFor( logging.TRACE ) else exc ))
        with open( Path( crypto_licensing.__file__ ).resolve().parent / 'licensing' / 'static' / 'txt' / 'CL-KEYPAIR-MISSING.txt', 'r' ) as f:
            error		= f.read().format(
                DISTRIBUTION	= deduce_name( basename=basename, filename=kwds.get( 'filename' ), package=kwds.get( 'package' ), default=client and client.servicekey or "" ),
                KEYPATTERN	= licensing.KEYPATTERN,
                LICENSE_OPTION	= '--license',
            )
        yield Process.FAILED, error

    else:
        yield Process.GRANTS, grants


def process(
    author: Optional[licensing.Agent]	= None,			# Details of the author's product we're licensing
    client: Optional[licensing.Agent]	= None,			# ..and the intended specific client Agent
    username: Optional[str]	= None,			# The credentials for our client Agent's Keypair
    password: Optional[str]	= None,
    basename		= None,
    registering			= None,
    acquiring			= None,
    **kwds
):
    """Load a License, or Process payment for and obtain a License, for certain client capabilities.

    Yields a sequence of prompts for any client information required, and yields the various
    credentials loaded/obtained, and finally (if successful) yields the License.

    Once the caller obtains the License, it should be verified.

    On the simplest path, reloads pre-existing Agent keypair and License files and yields them in
    order.  If the License(s) contain the requested capabilities Grants, then the process is
    complete.

    The Licenses may be associated with a Machine-ID, or have a limited lifetime; therefore, even if
    the Licenses may be loaded, they may not be valid (ie. if they've been loaded onto a new machine
    from backup, or have expired).

    If a License expires, it should contain the original Grants, and their costs (at the time the
    License was issued).  If a new License must be issued, the Grants/costs from the existing
    License must be respected in the new License, so that existing (historical) Cryptocurrency
    payments satisfy them.  Therefore, each Grant's LineItem data must be deducable from the
    existing License(s).  We must obtain the existing Licenses, then check them for validity.


    If certain Grants are insufficient (eg. if we can find Licenses containing a capability 5, and
    the caller requires 10, or if a certain capability is completely absent in the loaded Grants),
    then the remaining Grant must be acquired.

    If required Grants remain, then we attempt to process a variety of approaches to obtain one:

    1) The cost of the Grant is computed, and Invoice LineItems are produced enumerating them

    2) An Invoice PDF if produced, computing prices in various Cryptocurrencies

    3) The Invoice is approved via a PROMPT; when returned

        - if not approved, the process fails

    4) Payment is awaited via another PROMPT; when returned

       - the designated Cryptocurrency's blockchain is queried for payment
       - if no cryptocurrency designated, the process fails
       - if payment not (yet) received, issue an ERROR and loop awaiting payment

    5) When payment received, generate the appropriate License

       - Obtain them from a crypto-licensing server, via its signed API.  These will be signed
         by the Author's Agent,  and will be verifiable via DKIM (check=True).

       - Obtain them locally.  These will be signed by the local Client's Agent, and therefore will
         NOT be verifiable (check=False).  They will, however, provide proof that the local Client
         Agent produced them.

         - Of course, anyone versed in the state of the art can trivially take their local Agent's
           Ed25519 Keypair, and sign anything they wish - including such a License.  However, we are
           not protecting ourselves from determined thieves; we're supporting clients who wish to
           pay for and legitimately use our software.

    """
    if registering is None:
        # If we're provided w/ a client Agent (w/ a keypair or pubkey), we won't be registering one
        registering		= True if client is None else False
    if acquiring is None:
        acquiring		= True

    # We're looking for a License authored by an author Agent (eg. Dominion R&D Corp.), for a
    # certain product or service.  This might be encapsulated as one of the dependencies of the
    # License we find (eg. if Dominion issues a License to some company, which includes the ability
    # to run a crypto-licensing server), but we'll validate that the Grant was issued by Dominion
    # R&D Corp.  For example, Dominion issues a License to awesome-inc.com to sub-License
    # crypto-licensing servers.  They, in turn, issue a License to Лайка.ru to run a
    # crypto-licensing server, and help them set it up.  When
    # http://crypto-licensing.xn--80aa0aec.ru/ (crypto-licensing.Лайка.ru) issues a License for
    # their software, part of the fees are paid to awesome-inc.com and some to dominionrnd.com.  The
    # final software installation uses crypto-licensing's authorized() function, which checks that
    # each successive License's dependencies are correctly signed, and carries the original
    # 'crypto-licensing' Grant through to the recipient.
    dominion			= licensing.Agent(
        name	= licensing.COMPANY,
        domain	= licensing.DOMAIN,
        product	= "SLIP-39",
        pubkey	= licensing.PUBKEY,
    )

    reloader			= reload(
        author		= author or dominion,
        client		= client,
        username    	= username,
        password	= password,
        basename	= basename,
        registering	= registering,
        acquiring	= acquiring,
        **kwds
    )

    keypairs			= []
    grants			= None
    credentials			= None
    try:
        while True:
            key,val		= reloader.send( credentials )
            if key is Process.PROMPT:
                # User information is required; yield the prompt, send the returned data into reloader
                log.warning( f"Prompt: {val}" )
            # Some other key,val not returning input
            if key is Process.KEYPAIR:
                log.warning( f"Keypair: {val}" )
                keypairs.append( val )
            if key is Process.LICENSE:
                log.warning( f"License: {val[1]}" )
                keypairs.append( val[0] )
            if key is Process.GRANTS:
                grants		= val
            credentials		= ( yield (key,val) )
    except StopIteration:
        pass

    if grants:
        # TODO: check grants
        pass

    # No/insufficient license grants.  Engage the process of paying for and obtaining a License.
