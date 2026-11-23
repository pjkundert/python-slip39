import importlib
import pytest

from fpdf		import FlexTemplate

from .defaults		import BACKGROUNDS
from .layout		import write_pdfs
from .main		import main


@pytest.fixture
def rendered( monkeypatch ):
    """Records the texts and images of every template rendered into a PDF."""
    rendered			= []
    render			= FlexTemplate.render

    def record( self, *args, **kwds ):
        rendered.append( dict( self.texts ))
        return render( self, *args, **kwds )
    monkeypatch.setattr( FlexTemplate, 'render', record )
    return rendered


def backgrounds_printed( rendered ):
    """The things printed because of backgrounds: the cover image, the card's diagonal group labels, the
    watermark, and the Paper Wallet background and its diagonal cryptocurrency names."""
    return {
        k
        for t in rendered
        for k in t
        if k in ( 'cover-image', 'cover-fade', 'card-watermark', 'wallet-bg' ) or k.startswith(( 'card-g', 'crypto-f', 'crypto-b' ))
    }


def test_backgrounds( tmp_path, rendered ):
    pytest.importorskip( "Crypto.Protocol.KDF" )  # BIP-38 encrypted Paper Wallets require scrypt
    for backgrounds in ( False, True, None ):
        rendered.clear()
        write_pdfs(
            names		= [ "Test" ],
            master_secret	= bytes.fromhex( "ff" * 16 ),
            cryptocurrency	= [ "BTC" ],
            filepath		= str( tmp_path ),
            filename		= "backgrounds",
            watermark		= "Watermark",
            wallet_pwd		= "password",
            **( {} if backgrounds is None else dict( backgrounds=backgrounds )),  # None: the default
        )
        printed			= backgrounds_printed( rendered )
        if backgrounds is None:
            backgrounds		= BACKGROUNDS
        if backgrounds:
            assert { 'cover-image', 'cover-fade', 'card-watermark', 'wallet-bg' } <= printed
            assert any( k.startswith( 'card-g' ) for k in printed )
            assert any( k.startswith( 'crypto-f' ) for k in printed )
        else:
            assert not printed


def test_main_backgrounds( monkeypatch ):
    """--backgrounds and --no-backgrounds are passed on to write_pdfs."""
    calls			= []
    monkeypatch.setattr( importlib.import_module( 'slip39.main' ), 'write_pdfs', lambda **kwds: calls.append( kwds ) or {} )
    for args,expected in (( [], BACKGROUNDS ), ( [ '--backgrounds' ], True ), ( [ '--no-backgrounds' ], False )):
        assert main( [ '-q', *args, 'Test' ] ) == 0
        assert calls[-1]['backgrounds'] is expected
