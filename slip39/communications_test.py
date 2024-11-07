import logging
import os
import re
import sys
import pytest

from io			import StringIO
from pathlib		import Path
from subprocess		import Popen, PIPE
from email		import message_from_string


from aiosmtpd.controller import Controller

try:
    import dkim
    from .communications	import dkim_message, send_message, matchaddr, AutoResponder
except ImportError:
    dkim = None

from .defaults		import SMTP_TO, SMTP_FROM

log				= logging.getLogger( __package__ )

# Disable printing of details unless something goes wrong...
print_NOOP			= lambda *args, **kwds: None    # noqa: E731
print				= print_NOOP			# noqa: E273

# If we find a DKIM key, lets use it.  Otherwise, we'll just use the pre-defined pre-signed email.Message
dkim_keys			= list( Path( __file__ ).resolve().parent.parent.glob( 'licensing.dominionrnd.com.*.key' ))
dkim_key			= None
dkim_msg			= None
if dkim_keys:
    # Choose the latest available, assuming YYYYMMDD selector
    dkim_key			= str( sorted( dkim_keys )[-1] )
    dkim_selector		= re.match( r'.*\.(\d+)\.key', dkim_key ).group( 1 )
else:
    # No local key (the usual case, unless you're Dominion R&D!)
    dkim_selector		= '20221230'
    dkim_msg			= message_from_string( """\
Content-Type: multipart/alternative; boundary================1903566236404015660==
MIME-Version: 1.0
From: no-reply@licensing.dominionrnd.com
To: licensing@dominionrnd.com
Reply-To: perry@kundert.ca
Subject: Hello, world!
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/simple; d=licensing.dominionrnd.com; i=@licensing.dominionrnd.com; q=dns/txt; s=20221230; t=1673405994; h=from : to;\
 bh=RkF6KP4Q94MVDBEv7pluaWdzw0z0GNQxK72rU02XNcE=; b=Tao30CJGcqyX86f37pSrSFLSDvA8VkzQW0jiMf+aFg5D99LsUYmUZxSgnDhW2ZEzjwu6bzjkEEyvSEv8LxfDUW+AZZG3enbq/mnnUZw3PXp4l\
MaZGN9whvTIUy4/QUlMGKuf+7Vzi+8eKKjh4CWKN/UEyX6YoU7V5eyjTTA7q1jIjEl8jiM4LXYEFQ9LaKUmqqmRh2OkxBVf1QG+fEYTYUed+oS05m/d1SyVLjxv8ldeXT/mGgm1CrGk1qfRTzfcksX4qNAluTfJTa\
kDpHNPw0RX0QzkuWvgWG5GngV65yg6fL87wQOVqV4O7OhK6eTkzWqzNyerJd4i6B7ZCoYEUg==

--===============1903566236404015660==
Content-Type: text/plain; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit

Testing 123
--===============1903566236404015660==
Content-Type: text/html; charset="us-ascii"
MIME-Version: 1.0
Content-Transfer-Encoding: 7bit

<em>Testing 123</em>
--===============1903566236404015660==--

""" )


@pytest.mark.skipif( not dkim,
                     reason="DKIM support unavailable; install w/ [invoice] option" )
def test_communications_matchaddr():
    assert matchaddr( "abc+def@xyz", mailbox="abc", domain="xyz" ) == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz",                domain="xYz" ) == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz", mailbox="Abc"               ) == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz",                             ) == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz", "a*c","*f","x?z"            ) == ("abc", "def", "xyz")
    assert matchaddr( "abc+def@xyz", "b*c","*f","x?z"            ) is None
    assert matchaddr( "abc+def@xyz", "a*c","*f","x?"             ) is None
    assert matchaddr( "abc+def@xyz",                             )[2] == "xyz"
    assert matchaddr( "abc+def@xyz", mailbox="xxx"               ) is None


@pytest.mark.skipif( not dkim,
                     reason="DKIM support unavailable; install w/ [invoice] option" )
def test_communications_dkim():
    log.info( f"Using DKIM: {dkim_selector}: {dkim_key}" )
    if dkim_key:
        msg			= dkim_message(
            sender_email	= SMTP_FROM,			# Message From: specifies claimed sender
            to_email		= SMTP_TO,			# See https://dkimvalidator.com to test!
            reply_to_email	= "perry@kundert.ca",
            subject		= "Hello, world!",
            message_text	= "Testing 123",
            message_html	= "<em>Testing 123</em>",
            dkim_private_key_path = dkim_key,
            dkim_selector	= dkim_selector,
            headers		= ['From', 'To'],
        )
    else:
        msg			= dkim_msg

    log.info( f"DKIM {'signed' if dkim_key else 'canned'} Message:\n{msg}" )

    sig			= msg['DKIM-Signature']
    sig_kvs		= sig.split( ';' )
    sig_k_v		= dict(
        (k.strip(), v.strip())
        for k,v in ( kv.split( '=', 1 ) for kv in sig_kvs )
    )
    assert sig_k_v['v'] == '1'
    assert sig_k_v['a'] in ( 'rsa-sha256', 'ed25519-sha256' )

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
    try:
        send_message(
            msg,
            #from_addr	= SMTP_FROM,		# Envelope MAIL FROM: specifies actual sender
            #to_addrs	= [ SMTP_TO ],		# Will be the same as message To: (should default)
            #relay		= ['mail2.kundert.ca'],  # 'localhost',   # use eg. ssh -fNL 0.0.0.0:25:linda.mx.cloudflare.net:25 root@your.VPS.com
            #port		= 25,  # 465 --> SSL, 587 --> TLS (default),
            #usessl = False, starttls = False, verifycert = False,  # to mail.kundert.ca; no TLS
            #usessl = False, starttls = True, verifycert = False,  # default
        )
    except Exception as exc:
        # This may fail (eg. if you have no access to networking), so we don't check.
        log.warning( f"(Expected, if no networking): Failed to send DKIM-validated email to {SMTP_TO}: {exc}" )
        pass


@pytest.mark.skipif( not dkim,
                     reason="DKIM support unavailable; install w/ [invoice] option" )
def test_communications_autoresponder( monkeypatch ):
    """The Postfix-compatible auto-responder takes an email.Message from stdin, and auto-forwards it
    (via a relay; normally the same Postfix installation that it is running within).

    Let's shuttle a simple message through the AutoResponder, and fire up an SMTP daemon to receive
    the auto-forwarded message(s).

    """
    if dkim_key:
        msg			= dkim_message(
            sender_email	= SMTP_FROM,			# Message From: specifies claimed sender
            to_email		= SMTP_TO,			# See https://dkimvalidator.com to test!
            reply_to_email	= "perry@kundert.ca",
            subject		= "Hello, world!",
            message_text	= "Testing 123",
            message_html	= "<em>Testing 123</em>",
            dkim_private_key_path = dkim_key,
            dkim_selector	= dkim_selector,
            headers		= ['From', 'To'],
        )
    else:
        msg			= dkim_msg

    envelopes		= []

    class PrintingHandler:
        async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
            if matchaddr( address )[2] not in ('dominionrnd.com', 'kundert.ca'):
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

    # Send the email.Message directly to our SMTP daemon, w/ RCTP TO: licensing@dominionrnd.com
    # (taken from the To: header)
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
    ar				= AutoResponder(
        address		= SMTP_FROM,
        server		= controller.hostname,
        port		= controller.port,
        reinject	= False,
    )
    status			= ar(
        from_addr, *to_addrs
    )
    assert status == 0
    assert len( envelopes ) == 2
    assert envelopes[-1].rcpt_tos == [ 'perry@kundert.ca' ]

    # Now, try the CLI version.  Must use the current python interpreter, and this local instance of python-slip39
    here			= Path( __file__ ).resolve().parent

    for execute in [
        [
            sys.executable, "-m", "slip39.communications",
        ]

    ]:
        command			= list( map( str, execute + [
            '-vv', '--no-json',
            'autoresponder',
            '--server',		controller.hostname,
            '--port',		controller.port,
            #'--no-reinject',
            '--reinject',	"echo",
            '*@*licensing.dominionrnd.com',  # allow any sender mailbox, any ...licensing subdomain of dominionrnd.com
            from_addr,
            *to_addrs
        ] ))
        PYTHONPATH		= f"{here.parent}"
        log.info( f"Running filter w/ PYTHONPATH={PYTHONPATH}: {' . '.join( command )}" )
        with Popen(
                command,
                stdin	= PIPE,
                stdout	= PIPE,
                stderr	= PIPE,
                env	= dict(
                    os.environ,
                    PYTHONPATH	= PYTHONPATH,
                )) as process:
            out, err		= process.communicate( msg.as_bytes() )
            log.info( f"Filter stdout: {out.decode( 'UTF-8' ) if out else out}, stderr: {err.decode( 'UTF-8' ) if err else err}" )
            assert process.returncode == 0
    assert len( envelopes ) == 3
    assert envelopes[-1].rcpt_tos == [ 'perry@kundert.ca' ]
