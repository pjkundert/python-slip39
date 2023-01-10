from io			import StringIO

from pathlib		import Path

import dkim

from aiosmtpd.controller import Controller

from .email		import dkim_message, send_message, matchaddr, autoresponder
from ..defaults		import SMTP_TO, SMTP_FROM


dkim_key			= Path( __file__ ).resolve().parent.parent.parent / 'licensing.dominionrnd.com.20221230.key'
dkim_selector			= '20221230'


def test_email_dkim():
    msg				= dkim_message(
        sender_email	= SMTP_FROM,			# Message From: specifies claimed sender
        to_email	= SMTP_TO,			# See https://dkimvalidator.com to test!
        reply_to_email	= "perry@kundert.ca",
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


def test_email_matchaddr():
    assert matchaddr( "abc+def@xyz", mailbox="abc", domain="xyz" ).groups() == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz",                domain="xYz" ).groups() == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz", mailbox="Abc"               ).groups() == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz",                             ).groups() == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz",                             ).group( 3 ) == "xyz"
    assert matchaddr( "abc+def@xyz", mailbox="xxx"               ) is None


def test_email_autoresponder( monkeypatch ):
    """The Postfix-compatible autoresponder takes an email from stdin, and auto-forwards it (via a
    relay; normally the same Postfix installation that it is running within).

    Let's shuttle a simple message through the autoresponder, and fire up an SMTP daemon to receive
    the auto-forwarded message(s).

    """
    msg				= dkim_message(
        sender_email	= SMTP_FROM,			# Message From: specifies claimed sender
        to_email	= SMTP_TO,			# See https://dkimvalidator.com to test!
        reply_to_email	= "perry@kundert.ca",
        subject		= "Hello, world!",
        message_text	= "Testing 123",
        message_html	= "<em>Testing 123</em>",
        dkim_private_key_path = dkim_key,
        dkim_selector	= dkim_selector,
        headers		= ['From', 'To'],
    )

    envelopes		= []
    class PrintingHandler:
        async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
            if matchaddr( address ).group( 3 ) not in ('dominionrnd.com', 'kundert.ca'):
                return f'550 not relaying to {address}'
            envelope.rcpt_tos.append(address)
            return '250 OK'

        async def handle_DATA(self, server, session, envelope):
            print('Message from %s' % envelope.mail_from)
            print('Message for %s' % envelope.rcpt_tos)
            print('Message data:\n')
            for ln in envelope.content.decode('utf8', errors='replace').splitlines():
                print(f'> {ln}'.strip())
            print()
            print('End of message')
            envelopes.append( envelope )
            return '250 Message accepted for delivery'

    handler		= PrintingHandler()
    # dynamic port allocation w/ port=0 not scheduled 'til ~v1.5
    controller		= Controller( handler, hostname='localhost', port=11111 )
    controller.start()

    # Send the email.Message directly our SMTP daemon, w/ RCTP TO: licensing@dominionrnd.com (taken
    # from the To: header)
    send_message(
        msg,
        relay		= controller.hostname,
        port		= controller.port,
        starttls	= False,
        usessl		= False
    )
    assert len( envelopes ) == 1
    assert envelopes[-1].rcpt_tos == [ 'licensing@dominionrnd.com' ]

    # Now, run the auto-responder on messages to licensing@dominionrnd.com, not reinjecting the
    # message into the mail system, and sending the auto-response to the SMTP daemon.  We should see
    # it at the Reply-To: perry@kundert.ca header address.
    from_addr			= msg['From'] or msg['Sender']
    to_addrs			= []
    if 'To' in msg:
        to_addrs.append( msg['To'] )
    for cc in ('Cc', 'Bcc'):
        if cc in msg:
            to_addrs	       += map( str.strip, msg[cc].split( ',' ) )

    monkeypatch.setattr( 'sys.stdin', StringIO( msg.as_string() ))
    ar				= autoresponder(
        address		= SMTP_TO,
        server		= controller.hostname,
        port		= controller.port,
        reinject	= lambda *args, **kwds: None
    )
    ar.respond(
        from_addr, *to_addrs
    )
        
    assert len( envelopes ) == 2
    assert envelopes[-1].rcpt_tos == [ 'perry@kundert.ca' ]
