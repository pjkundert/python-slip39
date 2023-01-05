
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
import logging
import smtplib
import ssl

from tabulate		import tabulate
from email		import utils
from email.mime		import multipart, text

import dkim

from crypto_licensing.licensing import doh

from ..util		import is_listlike, commas


__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( 'email' )


def mx_records( domain, timeout=None ):
    """Query and yield the MX records for 'domain', via DoH, sorted by their priority."""
    kwds			= {}
    if timeout:
        kwds.update( timeout=timeout )
    for _,mx in sorted(
        mx['data'].split()
        for mx in doh.query(
            domain	= domain,
            record	= doh.DNSRecord.MX,
            **kwds
        )
    ):
        yield mx


def dkim_message(
    sender_email,			# The message From:; may be empty (but not for DKIM). For display by the client
    subject,
    message_text,
    message_html	= None,
    to_email		= None,		# The message To: "" ; may be "address, address".  For display by client
    cc_emails		= None,
    bcc_emails		= None,
    reply_to_email	= None,
    dkim_private_key_path="",
    dkim_selector	= "",
    signature_algorithm	= None,
    headers		= None,		# List of headers to DKIM-sign
):
    """

    Create a DKIM-signed email message.


    The `email` library assumes it is working with string objects.
    The `dkim` library assumes it is working with byte objects.
    This function performs the acrobatics to make them both happy.

   See:
       https://github.com/russellballestrini/miscutils/blob/master/miscutils/mail.py
       https://www.emailonacid.com/blog/article/email-deliverability/what_is_dkim_everything_you_need_to_know_about_digital_signatures/

    """

    if isinstance(message_text, bytes):
        # needed for Python 3.
        message_text = message_text.decode()

    if isinstance(message_html, bytes):
        # needed for Python 3.
        message_html = message_html.decode()

    if headers is None:
        headers			= ["From", "To", "Subject"]
    if signature_algorithm is None:
        signature_algorithm	= "rsa-sha256"  # "ed25519-sha256" not well supported, yet.

    sender_domain = sender_email.split("@")[-1]

    msg = multipart.MIMEMultipart("alternative")
    msg.attach(text.MIMEText(message_text, "plain"))
    if message_html:
        msg.attach(text.MIMEText(message_html, "html"))
    assert sender_email is not None, \
        "DKIM requires the From: address to be signed"
    msg["From"]			= sender_email
    if to_email is not None:
        msg["To"]		= ', '.join( to_email ) if is_listlike( to_email ) else to_email
    if cc_emails is not None:
        msg["Cc"]		= ', '.join( cc_emails ) if is_listlike( cc_emails ) else cc_emails
    if bcc_emails is not None:
        msg["Bcc"]		= ', '.join( bcc_emails ) if is_listlike( bcc_emails ) else bcc_emails
    if reply_to_email:
        # Autoresponders don't generally respect Reply-To (as recommended in RFC-3834)
        # https://www.rfc-editor.org/rfc/rfc3834#section-4.
        msg["Reply-To"] = reply_to_email
    msg["Subject"]		= subject

    try:
        # Python 3 libraries expect bytes.
        msg_data		= msg.as_bytes()
    except Exception:
        # Python 2 libraries expect strings.
        msg_data		= msg.as_string()

    if dkim_private_key_path and dkim_selector:
        # the dkim library uses regex on byte strings so everything
        # needs to be encoded from strings to bytes.
        with open(dkim_private_key_path) as fh:
            dkim_private_key	= fh.read()
        sig			= dkim.sign(
            message		= msg_data,
            selector		= str(dkim_selector).encode(),
            domain		= sender_domain.encode(),
            privkey		= dkim_private_key.encode(),
            include_headers	= [ h.encode() for h in headers ],
            signature_algorithm	= signature_algorithm.encode(),
        )
        #
        # Unfortunately, the produced:
        #
        #     b'DKIM-Signature: v=1; i=@lic...\r\n s=... b=Fp2...6H\r\n 5//6o...Ag=='
        #                                     ^^^^^                ^^^^^
        #
        # contains a bunch of errant whitespace, especially within the b: and bh: base-64 data
        #
        pre,sig_dirty		= sig.decode( 'utf-8' ).split( ':', 1 )
        log.info( f"DKIM signed: {sig_dirty!r}" )
        assert pre.lower() == "dkim-signature"

        # This seems to corrupt the signature, unexpectedly...
        #sig_kvs		= sig_dirty.split( ';' )
        #sig_k_v		= list(
        #    (k.strip(), ''.join(v.split()))  # eliminates internal v whitespace
        #    for k,v in ( kv.split( '=', 1 ) for kv in sig_kvs )
        #)
        #sig_clean		= '; '.join( f"{k}={v}" for k,v in sig_k_v )
        #log.info( f"DKIM clean:  {sig_clean!r}" )

        # add the dkim signature to the email message headers.
        # decode the signature back to string_type because later on
        # the call to msg.as_string() performs it's own bytes encoding...
        msg["DKIM-Signature"]	= sig_dirty.strip()   # sig_clean

        return msg


def send_message(
    msg,
    from_addr		= None,		# Envelope MAIL FROM: (use msg['Sender'/'From'] if not specified)
    to_addrs		= None,		# Envelope RCTP TO:   (use msg['To'/'CC'/'BCC'] if not specified)
    relay		= None,		# Eg. "localhost"; None --> lookup MX record
    port		= 587,		# Eg. 25 --> raw TCP/IP, 587 --> TLS, 465 --> SSL
    starttls		= True,		# Upgrade SMTP connection w/ TLS
    verifycert		= False,        # and verify SSL/TLS certs (not generally supported)
    usessl		= False,        # Connect using SMTP_SSL
    username		= None,
    password		= None,
):
    """Send a (possibly DKIM-signed) email msg, ideally directly to target domain's SMTP server,
    "RCPT TO" (each) to_addrs recipient, "MAIL FROM" the from_addrs.

    Unless relay(s) specified, we'll look up the MX records for each of the recipient to_addrs.

    """
    # Deduce from address / to addresses from message content, if not supplied.  These are the
    # Envelope MAIL FROM / RCPT TO addresses, which don't necessarily match From or To/CC/BCC.
    # See: smtplib.py's send_message.
    if from_addr is None:
        # Prefer the sender field per RFC 2822:3.6.2.
        from_addr		= msg['Sender'] if 'Sender' in msg else msg['From']
        from_addr		= utils.getaddresses( [from_addr] )[0][1]

    if to_addrs is None:
        addr_fields		= [
            f
            for f in (msg['To'], msg['Bcc'], msg['Cc'])
            if f is not None
        ]
        to_addrs		= [
            a[1]
            for a in utils.getaddresses( addr_fields )
        ]

    # Now that we have a to_addrs, construct a mapping of (mx, ...) --> [addr, ...].  For each
    # to_addrs, lookup its destination's mx records; we'll append all to_addrs w/ the same mx's
    # (sorted by priority).
    if relay is None:
        relay_addrs		= dict()
        for to in to_addrs:
            relay_addrs.setdefault( tuple( mx_records( to.split( '@', 1 )[1] )), [] ).append( to )
    else:
        if not is_listlike( relay ):
            relay		= [ relay ]
        relay_addrs[tuple( relay )] = to_addrs
    relay_max			= max( len( r ) for r in relay_addrs.keys() )
    addrs_max			= max( len( a ) for a in relay_addrs.values() )
    log.info( f"Relays, and their destination addresses\n" + tabulate(
        [
            list( r ) + ([ None ] * (relay_max - len( r ))) + list( a )
            for r,a in relay_addrs.items()
        ],
        headers= tuple( f"mx {m+1}" for m in range( relay_max ) ) + tuple( f"addr {a+1}" for a in range( addrs_max )),
        tablefmt='orgtbl'
    ))

    try:
        # Python 3 libraries expect bytes.
        msg_data = msg.as_bytes()
    except Exception:
        # Python 2 libraries expect strings.
        msg_data = msg.as_string()

    smtp_kwds			= dict()
    if usessl:
        smtp_class		= smtplib.SMTP_SSL
        smtp_kwds.update( context = ssl.create_default_context() )
        assert not ( starttls and verifycert ), \
            "starttls w/ verifycert is incompatible with usessl"
    else:
        smtp_class		= smtplib.SMTP

    class smtp_class_logging( smtp_class ):

        def putcmd( self, *args, **kwds ):
            log.info( f"SMTP --> {args!r} {kwds!r}" )
            return super().putcmd( *args, **kwds )

        def getreply( self ):
            try:
                errcode, errmsg = super().getreply()
                log.info( f"SMTP <-- {errcode} {errmsg}" )
                return errcode, errmsg
            except Exception as exc:
                log.info( f"SMTP <x- {exc}" )
                raise

    relayed			= 0
    for ra_i,(mxs, to_addrs) in enumerate( relay_addrs.items() ):
        log.warning( f"Sending {len(to_addrs)} via {mxs}: {to_addrs}" )
        for mx_i,mx in enumerate( mxs ):
            # TODO: react if connecting to relay (localhost postfix) is a socket error.
            log.info( f"Connecting to SMTP server {mx}" )
            try:
                with smtp_class_logging( mx, port, **smtp_kwds ) as mta:
                    if starttls:
                        if verifycert:
                            mta.starttls( context=ssl.create_default_context() )
                        else:
                            mta.starttls()
                    if username and password:
                        mta.auth( mta.auth_plain, user=username, password=password )
                    mta.sendmail( from_addr=from_addr, to_addrs=to_addrs, msg=msg_data )
            except Exception as exc:
                # If this is the last of the relays, and its last MX, and nothing was
                # successfully relayed, then raise the Exception.
                err			= f"Failed to send via SMTP relay {mx}: {exc}"
                log.warning( err )
                if mx_i + 1 == len( mxs ) and ra_i + 1 == len( relay_addrs ) and not relayed:
                    raise RuntimeError( err ) from exc
            else:
                #  Otherwise, the mail was successfully relayed at least once.
                relayed	       += 1
                log.info( f"Sent SMTP email via relay {mx} MAIL FROM: {from_addr} RCPT TO: {commas( to_addrs, final='and' )}" )
                break

    log.info( f"{relayed} of {len( relay_addrs )} relays succeeded" )

    return msg
