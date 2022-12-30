
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

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
# catch socket errors when postfix isn't running...
#from socket import error as socket_error

import dkim

from crypto_licensing.licensing import doh

from ..util		import is_listlike
from ..defaults		import SMTP_TO, SMTP_FROM

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( 'email' )


def mx_records( domain, timeout=None ):
    """Query and return the MX records for 'domain', via DoH."""
    kwds			= {}
    if timeout:
        kwds.update( timeout=timeout )
    return doh.query( domain=domain, record=doh.DNSRecord.MX, **kwds )


def smtp_send( subject, fr=None, to=None, lines=None, reply_from=None ):
    """
    Sends a message with 'subject', 'to' a list of addresses,
    optionally from address 'fr'.
    """
    try:
        smtp                    = smtplib.SMTP( 'localhost' )
        try:
            if not subject:
                subject         = '(no subject)'
            if to is None:
                to              = SMTP_TO
            if not is_listlike( to ):
                to              = [ to ]
            if not lines:
                lines           = []
            if fr is None:
                fr              = SMTP_FROM

            smtp.sendmail(
                fr, to,
                "From: %s\r\nSubject: %s\r\nTo: %s\r\n\r\n%s" % (
                    fr, subject, ', '.join( to ),
                    '\r\n'.join( lines )
                )
            )
        finally:
            smtp.quit()
    except Exception as exc:
        log.warning( "Failed to send email: %s" % exc )


def smtp_send_dkim(
    to_email,
    sender_email,
    subject,
    message_text,
    message_html=None,
    reply_to_email=None,
    relay="localhost",
    dkim_private_key_path="",
    dkim_selector="",
    signature_algorithm=None,
    headers=None,		# List of headers to DKIM-sign
):
    """

    Send DKIM-signed email.

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
        headers			= ["To", "From", "Subject"]
    if signature_algorithm is None:
        signature_algorithm	= "ed25519-sha256"

    sender_domain = sender_email.split("@")[-1]
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText(message_text, "plain"))
    if message_html:
        msg.attach(MIMEText(message_html, "html"))
    msg["To"] = to_email
    msg["From"] = sender_email
    if reply_to_email:
        msg["Reply-To"] = reply_to_email
    msg["Subject"] = subject

    try:
        # Python 3 libraries expect bytes.
        msg_data = msg.as_bytes()
    except Exception:
        # Python 2 libraries expect strings.
        msg_data = msg.as_string()

    if dkim_private_key_path and dkim_selector:
        # the dkim library uses regex on byte strings so everything
        # needs to be encoded from strings to bytes.
        with open(dkim_private_key_path) as fh:
            dkim_private_key = fh.read()
        sig = dkim.sign(
            message		= msg_data,
            selector		= str(dkim_selector).encode(),
            domain		= sender_domain.encode(),
            privkey		= dkim_private_key.encode(),
            include_headers	= [ h.encode() for h in headers ],
            signature_algorithm	= signature_algorithm.encode(),
        )
        # Unfortunately, the produced:
        #
        #     b'DKIM-Signature: v=1; a=...; ...\r\n s=... b=Fp2...6H\r\n 5//6o...Ag=='
        #                                      ^^^^^                ^^^^^
        #
        # contains a bunch of errant whitespace, especially within the b: and bh: base-64 encoded
        # data.
        pre,sig_dirty		= sig.decode( 'utf-8' ).split( ':', 1 )
        log.info( f"DKIM signed: {sig_dirty!r}" )
        assert pre.lower() == "dkim-signature"
        sig_kvs			= sig_dirty.split( ';' )
        sig_d			= dict(
            (k.strip(), ''.join(v.split()))  # eliminates internal v whitespace
            for k,v in ( kv.split( '=', 1 ) for kv in sig_kvs )
        )
        sig_clean		= '; '.join( f"{k}={v}" for k,v in sig_d.items() )
        log.info( f"DKIM clean:  {sig_clean!r}" )
        # add the dkim signature to the email message headers.
        # decode the signature back to string_type because later on
        # the call to msg.as_string() performs it's own bytes encoding...
        msg["DKIM-Signature"]	= sig_clean

        try:
            # Python 3 libraries expect bytes.
            msg_data = msg.as_bytes()
        except Exception:
            # Python 2 libraries expect strings.
            msg_data = msg.as_string()

    # TODO: react if connecting to relay (localhost postfix) is a socket error.
    s = smtplib.SMTP(relay)
    s.sendmail(sender_email, [to_email], msg_data)
    s.quit()
    return msg
