from typing			import Any, Dict, Iterable, List, NamedTuple, Sequence, Set, Tuple

from fpdf		import FPDF

from .generate		import create

FILE_DEFAULT			= "ethereum-SLIP-39.pdf"

class PDF( FPDF ):
    pass

def output(
    mnemonics: List[List[str]],
    account,
    filename		= None,
):
    pdf			= PDF(
        orientation	= 'L',
        unit		= 'in',
        format		= (3, 5),
    )
    pdf.add_page()
    pdf.set_font( 'Arial', 'B', 16 )
    pdf.cell( 2.5, 4.5, "Hello, world!" )
    pdf.output( filename or FILE_DEFAULT )
