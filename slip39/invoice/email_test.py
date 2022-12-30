from pathlib		import Path

from .email		import smtp_send_dkim


def test_email_dkim():
    dkim_key		= Path( __file__ ).resolve().parent.parent.parent / 'licensing.dominionrnd.com.20221230.key'
    dkim_selector	= '20221230'

    msg			= smtp_send_dkim(
        to_email	= "perry@kundert.ca",
        sender_email	= "no-reply@licensing.dominionrnd.com",
        subject		= "Hello, world!",
        message_text	= "Testing 123",
        message_html	= "<em>Testing 123</em>",
        dkim_private_key_path = dkim_key,
        dkim_selector	= dkim_selector,
        headers		= ['From', 'To'],
    )

    assert msg['DKIM-Signature'].startswith(
        'v=1; a=ed25519-sha256; c=relaxed/simple; d=licensing.dominionrnd.com; i=@licensing.dominionrnd.com; q=dns/txt; s=20221230; t='
    )
