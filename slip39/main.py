import argparse
import io
import logging
import math
import os
import re

from datetime	import datetime
from typing	import Any, Dict, Iterable, List, NamedTuple, Sequence, Set, Tuple

import qrcode
import eth_account
from fpdf	import FPDF

from .generate	import create, PATH_ETH_DEFAULT


log				= logging.getLogger( __package__ )

def organize_mnemonic( mnemonic, rows = 7, cols = 3, label="" ):
    """Given a "word word ... word" or ["word", "word", ..., "word"] mnemonic, emit rows organized in
    the desired rows and cols.  We return the fullly formatted line, plus the list of individual
    words in that line."""
    if isinstance( mnemonic, str ):
        mnemonic		= mnemonic.split( ' ' )
    num_words		= dict(
        (i, f"{i+1:>2d} {w}")
        for i,w in enumerate( mnemonic )
    )
    rows,cols		= 7,3
    for r in range( rows ):
        line		= label if r == 0 else ' ' * len( label )
        words		= []
        for c in range( cols ):
            if word := num_words.get( c*rows+r ):
                words.append( word )
                line   += f"{word:<13}"
        yield line,words


def output(
    name: str,
    group_threshold: int,
    groups: Dict[str,Tuple[int,List[str]]],
    accounts: Dict[str, eth_account.Account],
):
    size		= (3, 5)
    margin		= .25

    pdf				= FPDF(
        orientation	= 'L',
        unit		= 'in',
        format		= size,
    )
    pdf.set_margin( margin )
    fonts		= dict(
        sans	= 'helvetica',
        mono	= 'courier',
    )

    '''
    for font,style in ( ('FreeSans', ''), ('FreeSansB','B'), ('FreeMono' ):
        pdf.add_font( font.lower(), fname=os.path.join( os.path.dirname( __file__ ), 'fonts', font+'.ttf' ), uni=True )
    '''
    group_reqs			= list(
        f"{g_nam}({g_of}/{len(g_mns)})" if g_of != len(g_mns) else f"{g_nam}({g_of})"
        for g_nam,(g_of,g_mns) in groups.items() )
    requirements		= f"Need {group_threshold} of {', '.join(group_reqs)} to recover."

    # Output the first account path and address QR code
    qr				= None
    for path,acct in accounts.items():
        log.info( f"ETH({path:16}): {acct.address}" )
        qrc			= qrcode.QRCode(
            version	= None,
            error_correction = qrcode.constants.ERROR_CORRECT_M,
            box_size	= 10,
            border	= 0
        )
        qrc.add_data( acct.address )
        qrc.make( fit=True )
        if qr is None:
            qr			= qrc.make_image()
        if log.isEnabledFor( logging.INFO ):
            f			= io.StringIO()
            qrc.print_ascii( out=f )
            f.seek( 0 )
            for l in f:
                log.info( f"{l.strip()}" )

    assert qr, "At least one ETH account must be supplied"
    for g_num,(g_name,(g_of,g_mnems)) in enumerate( groups.items() ):
        log.info( f"{g_name}({g_of}/{len(g_mnems)}): {requirements}" )
        for mn_num,mnem in enumerate( g_mnems ):
            pdf.add_page()

            qr_siz		= pdf.eph / 2
            pdf.image( qr.get_image(), h=qr_siz, w=qr_siz, x=pdf.epw + margin - qr_siz, y=pdf.eph + margin - qr_siz )
                
            pdf.set_font( fonts['sans'], size=16 )
            line_height	= pdf.font_size * 1.5
            pdf.cell( pdf.epw, line_height,
                      f"SLIP39 **{g_name}({mn_num+1}/{len(g_mnems)})** for: {name}", markdown=True )
            pdf.ln( line_height )

            pdf.set_font( size=12 )
            line_height	= pdf.font_size * 1.5
            pdf.cell( pdf.epw, line_height, requirements )
            pdf.ln( line_height )

            pdf.set_font( size=8 )
            line_height	= pdf.font_size * 2
            pdf.cell( pdf.epw, line_height,
                      f"ETH({path}): {acct.address}{'...' if len(accounts)>1 else ''}" )
            pdf.ln( line_height )

            pdf.set_font( fonts['mono'], size=10 )
            line_height	= pdf.font_size * 1.65
            num_words		= dict( (i, f"{i+1:>2d} {w}")
                                        for i,w in enumerate( mnem.split( ' ' )))
            col_width		= pdf.epw / 4
            
            rows,cols		= 7,3
            for line,words in organize_mnemonic(
                    mnem, rows=rows, cols=cols, label=f"  {mn_num+1}: "):
                log.info( line )
                for word in words:
                    pdf.multi_cell( col_width, line_height, word,
                                    border=False, ln=3, max_line_height=pdf.font_size )
                pdf.ln( line_height )

    return pdf,accounts


log_cfg				= {
    "level":	logging.WARNING,
    "datefmt":	'%Y-%m-%d %H:%M:%S',
    #"format":	'%(asctime)s.%(msecs).03d %(threadName)10.10s %(name)-8.8s %(levelname)-8.8s %(funcName)-10.10s %(message)s',
    "format":	'%(asctime)s %(name)-8.8s %(message)s',
}


def group_parser( group_spec ):
    match			= group_parser.RE.match( group_spec )
    if not match:
        raise ValueError( f"Invalid group specification: {group_spec!r}" )
    name			= match.group( 'name' )
    size			= match.group( 'size' )
    require			= match.group( 'require' )
    if not size:
        size			= 1
    if not require:
        require			= math.ceil( int( size ) / 2. ) # eg. default 2/4, 3/5
    return name,(int(require),int(size))
group_parser.RE			= re.compile(
    r"""^
        \s*
        (?P<name> [^\d\(/]+ )
        \s*\(?\s*
        (:? (?P<require> \d* ) \s* / )?
        \s*
        (?P<size> \d* )
        \s*\)?\s*
        $""", re.VERBOSE )


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Create and output SLIP39 encoded Ethereum wallet(s) to a PDF file.",
        epilog = "" )
    ap.add_argument( '-v', '--verbose', action="count",
                     default=0, 
                     help="Display logging information." )
    ap.add_argument( '-o', '--output',
                     default="{name}-{date}+{time}-{address}.pdf",
                     help="Output PDF to file or '-' (stdout); formatting w/ name, date, time and address allowed" )
    ap.add_argument( '-t', '--threshold',
                     default=None,
                     help="Number of groups required for recovery (default: half of groups, rounded up)" )
    ap.add_argument( '-g', '--group', action='append',
                     help="A group name[[<require>/]<size>] (default: <size> = 1, <require> = half of <size>, rounded up, eg. 'Fren(3/5)' )." )
    ap.add_argument( '-p', '--path', action='append',
                     help=f"A derivation path (default: {PATH_ETH_DEFAULT})" )
    ap.add_argument( 'names', nargs="*",
                     help="Account names to produce")
    args			= ap.parse_args( argv )


    levelmap 			= {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    log_cfg['level']		= ( levelmap[args.verbose] 
                                    if args.verbose in levelmap
                                    else logging.DEBUG )
    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    groups			= dict(
        group_parser( g )
        for g in args.group or [ "First1", "Second(1/1)", "Fam(4)", "Fren/5" ]
    )
    group_threshold		= args.threshold or math.ceil( len( groups ) / 2. )

    for name in args.names or [ "" ]:
        pdf,accounts		= output(
            *create(
                name	= name,
                group_threshold = group_threshold,
                groups	= groups,
                paths	= args.path,
            )
        )
        now			= datetime.now()
        address			= accounts[next(iter(accounts.keys()))].address
        filename		= args.output.format(
            name	= name or "SLIP39",
            date	= datetime.strftime( now, '%Y-%m-%d' ),
            time	= datetime.strftime( now, '%H.%M.%S'),
            address	= address,
        )
        pdf.output( filename )
        log.warning( f"Wrote SLIP39-encoded wallet for {name!r} to: {filename}" )

    return 0
