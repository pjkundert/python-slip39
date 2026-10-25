import argparse
import pytest

from .defaults		import PAPER_FORMATS
from .main		import main, paper_format


def test_paper_format():
    """Paper sizes are case-insensitive names from PAPER_FORMATS, converted to their format value."""
    assert paper_format( 'a4' ) == paper_format( 'A4' ) == PAPER_FORMATS['A4']
    assert paper_format( 'photo' ) == PAPER_FORMATS['Photo']  # eg. (w,h) in mm; not a paper name known to the PDF library
    for unsupported in ( 'a5', 'a3', 'tabloid', '' ):
        with pytest.raises( argparse.ArgumentTypeError ) as exc:
            paper_format( unsupported )
        assert "Unsupported paper size" in str( exc.value )
        assert all( paper in str( exc.value ) for paper in PAPER_FORMATS )


def test_main_paper( tmp_path, monkeypatch, capsys ):
    monkeypatch.chdir( tmp_path )
    # An unsupported paper size is refused up front, w/ a one-line message
    with pytest.raises( SystemExit ) as exc:
        main( [ '-q', '-c', 'BTC', '--paper', 'a5', 'Test' ] )
    assert exc.value.code == 2
    assert "Unsupported paper size 'a5'" in capsys.readouterr().err
    assert not list( tmp_path.glob( '*.pdf' ))

    # Supported sizes are produced
    for paper in ( 'a4', 'Photo' ):
        assert main( [ '-q', '-c', 'BTC', '--paper', paper, '-o', f"paper-{paper}", 'Test' ] ) == 0
        assert ( tmp_path / f"paper-{paper}.pdf" ).stat().st_size > 0
