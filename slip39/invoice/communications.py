#! /usr/bin/env python3
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
import re
import smtplib
import ssl
import sys

from subprocess		import Popen, PIPE

import click
import dkim

from tabulate		import tabulate
from email		import utils, message_from_file
from email.mime		import multipart, text
from crypto_licensing.licensing import doh

from ..util		import is_listlike, commas, uniq, log_cfg, log_level


__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2023 Dominion Research & Development Corp."
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


def matchaddr( address, mailbox=None, domain=None ):
    """The supplied email address begins with "<mailbox>", optionally followed by a "+<extension>", and
    then ends with "@<domain>".  If so, return the re.match w/ the 3 groups.  If either 'mailbox' or
    'domain' is falsey, any will be allowed.

    Does not properly respect email addresses with quoting, eg. 'abc"123@456"@domain.com' because,
    quite frankly, I don't want to and that's just "Little Bobby Tables" (https://xkcd.com/327/)
    level asking for trouble...

    Simple <mailbox>[+<extension>]@<domain>, please.

    """
    return re.match(
        rf"(^{mailbox if mailbox else '[^@+]*'})(?:\+([^@]+))?@({domain if domain else '.*'})",
        utils.parseaddr( address )[1],
        re.IGNORECASE
    )


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

    sender_domain		= matchaddr( sender_email ).group( 3 )

    msg				= multipart.MIMEMultipart("alternative")
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
        msg["Reply-To"]		= reply_to_email
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
        # contains a bunch of unnecessary whitespace, especially within the b: and bh: base-64
        # data.  However, this whitespace is ignored by the standard email.Message parser.
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
        msg["DKIM-Signature"]	= sig_dirty.strip()

        return msg


def send_message(
    msg,
    from_addr		= None,		# Envelope MAIL FROM: (use msg['Sender'/'From'] if not specified)
    to_addrs		= None,		# Envelope RCTP TO:   (use msg['To'/'CC'/'BCC'] if not specified)
    relay		= None,		# Eg. "localhost"; None --> lookup MX record
    port		= None,		# Eg. 25 --> raw TCP/IP, 587 --> TLS (default), 465 --> SSL
    starttls		= None,		# Upgrade SMTP connection w/ TLS (default: True iff port == 587)
    usessl		= None,		# Connect using SMTP_SSL (default: True iff port == 465)
    verifycert		= None,		# and verify SSL/TLS certs (not generally supported)
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
    relay_addrs			= {}
    if relay is None:
        for to in to_addrs:
            relay_addrs.setdefault( tuple( mx_records( to.split( '@', 1 )[1] )), [] ).append( to )
    else:
        if not is_listlike( relay ):
            relay		= [ relay ]
        relay_addrs[tuple( relay )] = to_addrs
    relay_max			= max( len( r ) for r in relay_addrs.keys() )
    addrs_max			= max( len( a ) for a in relay_addrs.values() )
    log.info( "Relays, and their destination addresses\n" + tabulate(
        [
            list( r ) + ([ None ] * (relay_max - len( r ))) + list( a )
            for r,a in relay_addrs.items()
        ],
        headers= tuple( f"mx {m+1}" for m in range( relay_max ) ) + tuple( f"addr {a+1}" for a in range( addrs_max )),
        tablefmt='orgtbl'
    ))

    # Default port and TLS/SSL if unspecified.
    if port is None:
        port			= 587
    if starttls is None:
        starttls		= True if port == 587 else False
    if usessl is None:
        usessl			= True if port == 465 else False
    if verifycert is None:
        verifycert		= False

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


class PostQueue:
    """A postfix-compatible post-queue filter.  See:
    https://codepoets.co.uk/2015/python-content_filter-for-postfix-rewriting-the-subject/

    Receives an email via stdin, and re-injects it into the mail system via /usr/sbin/sendmail,
    raising an exception if for any reason it is unable to do so (caller should trap and return
    an appropriate exit status compatible w/ postfix:

         0: success
        69: bounce
        75: tempfail

    Creates and sends a response email via SMTP to a relay (default is the local SMTP server at
    localhost:25)

    The msg, from_addr and to_addrs are retained in self.msg, etc.

    Postfix will pass all To:, Cc: and Bcc: recipients in to_addrs.

    The reinject command is executed/called, and passed from_addr and *to_addrs; False disables.
    """
    def __init__( self, reinject=None ):
        if reinject in (None, True):
            reinject		= [ '/usr/sbin/sendmail', '-G', '-i', '-f' ]
        if is_listlike( reinject ):
            self.reinject	= list( map( str, reinject ))
        elif not reinject:
            self.reinject	= lambda *args: None		# False, ''
        else:
            self.reinject	= reinject			# str, callable
        log.info( f"Mail reinjection: {self.reinject!r}" )

    def respond( self, from_addr, *to_addrs ):
        msg			= self.message()
        try:
            # Allow a command (list), a shell command or a function for reinject
            err			= None
            if is_listlike( self.reinject ):
                with Popen(
                        self.reinject + [ from_addr] + list( to_addrs ),
                        stdin	= PIPE,
                        stdout	= PIPE,
                        stderr	= PIPE
                ) as process:
                    out, err	= process.communicate( msg.as_bytes() )
                    out		= out.decode( 'UTF-8' )
                    err		= err.decode( 'UTF-8' )
            elif isinstance( self.reinject, str ):
                with Popen(
                        f"{self.reinject} {from_addr} {' '.join( to_addrs )}",
                        shell	= True,
                        stdin	= PIPE,
                        stdout	= PIPE,
                        stderr	= PIPE
                ) as process:
                    out, err	= process.communicate( msg.as_bytes() )
                    out		= out.decode( 'UTF-8' )
                    err		= err.decode( 'UTF-8' )
            else:
                out		= self.reinject( from_addr, *to_addrs )
            log.info( f"Results of reinjection: stdout: {out}, stderr: {err}" )
        except Exception as exc:
            log.warning( f"Re-injecting message From: {from_addr}, To: {commas( to_addrs )} via sendmail failed: {exc}" )
            raise
        return msg

    def message( self ):
        """Return (a possibly altered) email.Message as the auto-response.  By default, an filter
        receives its email.Message from stdin, unaltered.

        """
        msg			= message_from_file( sys.stdin )
        return msg

    def response( self, msg ):
        """Prepare the response message.  Normally, it is at least just a different message."""
        msg
        return msg


class AutoResponder( PostQueue ):
    def __init__( self, *args, address=None, server=None, port=None, **kwds ):
        m			= matchaddr( address or '' )
        assert m, \
            f"Must supply a valid email destination address to auto-respond to: {address}"
        self.address		= address
        self.mailbox,self.extension,self.domain	= m.groups()
        self.relay		= 'localhost' if server is None else server
        self.port		= 25 if port is None else port

        super().__init__( *args, **kwds )

        log.info( f"autoresponding to DKIM-signed emails To: {self.address}@{self.domain}" )

    def respond( self, from_addr, *to_addrs ):
        """Decide if we should auto-respond, and do so."""

        msg			= super().respond( from_addr, *to_addrs )
        log.info( f"Filtered From: {msg['from']}, To: {msg['to']}"
                  f" originally     from {from_addr} to {len(to_addrs)} recipients: {commas( to_addrs, final='and' )}" )

        if 'to' not in msg or not matchaddr( msg['to'], mailbox=self.mailbox, domain=self.domain ):
            log.warning( f"Message From: {msg['from']}, To: {msg['to']} expected To: {self.address}; not auto-responding" )
            return 0
        if 'dkim-signature' not in msg:
            log.warning( f"Message From: {msg['from']}, To: {msg['to']} is not DKIM signed; not auto-responding" )
            return 0
        if not dkim.verify( msg.as_bytes() ):
            log.warning( f"Message From: {msg['from']}, To: {msg['to']} DKIM signature fails; not auto-responding " )
            return 0

        # Normalize, uniqueify and filter the addresses (discarding invalids).  Avoid sending it to
        # the designated self.address, as this would set up a mail loop.
        to_addrs_filt		= [
            fa
            for fa in uniq( filter( None, (
                utils.parseaddr( a )[1]
                for a in to_addrs
            )))
            if fa != self.address
        ]

        rsp			= self.response( msg )
        # Also use the Reply-To: address, if supplied
        if 'reply-to' in rsp:
            _,reply_to		= utils.parseaddr( rsp['reply-to'] )
            if reply_to not in to_addrs_filt:
                to_addrs_filt.append( reply_to )

        log.info( f"Response From: {rsp['from']}, To: {rsp['to']}"
                  f" autoresponding from {from_addr} to {len(to_addrs_filt)} recipients: {commas( to_addrs_filt, final='and' )}"
                  + ( f" (was {len(to_addrs)}: {commas( to_addrs, final='and' )})" if to_addrs != to_addrs_filt else "" ))

        # Now, send the same message to all the supplied Reply-To, and Cc/Bcc address (already in
        # responder.to_addrs).  If it is DKIM signed, since we're not adjusting the message -- just
        # send w/ new RCPT TO: envelope addresses.  We'll use the same from_addr address (it must be
        # from our domain, or we wouldn't be processing it.
        try:
            send_message(
                rsp,
                from_addr	= from_addr,
                to_addrs	= to_addrs_filt,
                relay		= self.relay,
                port		= self.port,
            )
        except Exception as exc:
            log.warning( f"Message From: {rsp['from']}, To: {rsp['to']} autoresponder SMTP send failed: {exc}" )
            return 75  # tempfail

        return 0


@click.group()
@click.option('-v', '--verbose', count=True)
@click.option('-q', '--quiet', count=True)
@click.option( '--json/--no-json', default=True, help="Output JSON (the default)")
def cli( verbose, quiet, json ):
    cli.verbosity		= verbose - quiet
    log_cfg['level']		= log_level( cli.verbosity )
    logging.basicConfig( **log_cfg )
    if verbose or quiet:
        logging.getLogger().setLevel( log_cfg['level'] )
    cli.json			= json
cli.verbosity			= 0  # noqa: E305
cli.json			= False


@click.command()
@click.argument( 'address', nargs=1 )
@click.argument( 'from_addr', nargs=1 )
@click.argument( 'to_addrs', nargs=-1 )
@click.option( '--server', default='localhost' )
@click.option( '--port', default=25 )
@click.option( '--reinject', type=str, default=None, help="A custom command to reinject email, eg. via sendmail" )
@click.option( '--no-reinject', 'reinject', flag_value='', help="Disable reinjection of filtered mail, eg. via sendmail" )
def autoresponder( address, from_addr, to_addrs, server, port, reinject ):
    """Run an auto-responder that replies to all incoming emails to the specified email address.

    Will be invoked with a from_addr and 1 or more to_addrs.

    - Must be DKIM signed, including the From: and To: addresses.
    - The RCPT TO: "envelope" address must match 'address':
      - We won't autorespond to copies of the email being delivered to other inboxes
    - The MAIL FROM: "envelope" address must match the From: address
      - We won't autorespond to copies forwarded from other email addresses


    Configure Postfix system as per: https://github.com/innovara/autoreply, except create

        # autoresponder pipe
        autoreply unix  -       n       n       -       -       pipe
         flags= user=autoreply null_sender=
         argv=python -m slip39.email autoresponder licensing@dominionrnd.com ${sender} ${recipient}

    """
    AutoResponder(
        address		= address,
        server		= server,
        port		= port,
        reinject	= reinject,
    ).respond( from_addr, *to_addrs )


cli.add_command( autoresponder )


if __name__ == "__main__":
    cli()
