from pathlib		import Path

import dkim

from .email		import dkim_message, send_message
from ..defaults		import SMTP_TO, SMTP_FROM


def test_email_dkim():
    dkim_key		= Path( __file__ ).resolve().parent.parent.parent / 'licensing.dominionrnd.com.20221230.key'
    dkim_selector	= '20221230'

    msg			= dkim_message(
        sender_email	= SMTP_FROM,			# Message From: specifies claimed sender
        to_email	= SMTP_TO,			# See https://dkimvalidator.com to test!
        cc_emails	= "perry@kundert.ca",
        subject		= "Hello, world!",
        message_text	= "Testing 123",
        message_html	= "<em>Testing 123</em>",
        dkim_private_key_path = dkim_key,
        dkim_selector	= dkim_selector,
        headers		= ['From', 'To'],
    )

    assert msg['DKIM-Signature'].startswith(
        'v=1; a=rsa-sha256; c=relaxed/simple;'  # ' d=licensing.dominionrnd.com; i=@licensing.dominionrnd.com; q=dns/txt; s=20221230; t='
    )
    assert dkim.verify( msg.as_bytes() )

    # Send via port 587 w/ TLS.  Use the appropriate relay servers.  The cloudflare MX servers only
    # respond on port 25; TLS port 587 don't see to respond Since port 25 is usually blocked for
    # most retail internet connections, we'll use our own TLS-capable relays.  So: for normal,
    # retail ISP-connected hosts, sending SMTP email via port 25 is usually impossible.  Via port
    # 587 (TLS) or 465 (SSL), it might be possible.
    # 
    # Altering the MAIL FROM: (and hence the email's Return-Path), you can alter the behaviour of
    # auto-responders.  However, SPF analysis looks at the Return-Path to determine which domain's
    # TXT records to examine!  Therefore, the act of changing the MAIL FROM: address to the intended
    # recipient of the auto-response, makes it certain that any SPF record on the intended
    # recipient's domain will mark this email with an Received-SPF: fail!
    # 
    # There doesn't appear to be a strictly "legal" method in SMTP to designate the intended
    # recipient of the response.  I guess, to avoid using "bounces" to send SPAM email.  Therefore,
    # the auto-responder must be programmed to use the Reply-To address -- something that eg. Gmail
    # cannot be programmed to do.
    send_message(
        msg,
        #from_addr	= SMTP_FROM,		# Envelope MAIL FROM: specifies actual sender
        #to_addrs	= [ SMTP_TO ],		# Will be the same as message To: (should default)
        #relay		=  ['mail2.kundert.ca'],  # 'localhost',   # use eg. ssh -fNL 0.0.0.0:25:linda.mx.cloudflare.net:25 root@your.VPS.com
        #port		= 25,  # 465 --> SSL, 587 --> TLS (default),
        #usessl = False, starttls = False, verifycert = False,  # to mail.kundert.ca; no TLS
        #usessl = False, starttls = True, verifycert = False,  # default
    )
