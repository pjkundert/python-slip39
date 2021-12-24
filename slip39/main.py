import argparse
import io
import logging
import math
import re

from collections import namedtuple
from datetime	import datetime
from typing	import Dict, List, Tuple

import qrcode
import eth_account
from fpdf	import FPDF, FlexTemplate

from .generate	import create, PATH_ETH_DEFAULT


log				= logging.getLogger( __package__ )


def enumerate_mnemonic( mnemonic ):
    if isinstance( mnemonic, str ):
        mnemonic		= mnemonic.split( ' ' )
    return dict(
        (i, f"{i+1:>2d} {w}")
        for i,w in enumerate( mnemonic )
    )


def organize_mnemonic( mnemonic, rows = 7, cols = 3, label="" ):
    """Given a "word word ... word" or ["word", "word", ..., "word"] mnemonic, emit rows organized in
    the desired rows and cols.  We return the fully formatted line, plus the list of individual
    words in that line."""
    num_words			= enumerate_mnemonic( mnemonic )
    for r in range( rows ):
        line			= label if r == 0 else ' ' * len( label )
        words			= []
        for c in range( cols ):
            word		= num_words.get( c * rows + r )
            if word:
                words.append( word )
                line	       += f"{word:<13}"
        yield line,words


class Region:
    """Takes authority for a portion of another Region, and places things in it, relative to its
    upper-left and lower-right corners."""
    def __init__( self, name, x1=None, y1=None, x2=None, y2=None, rotation=None ):
        self.name		= name
        self.x1			= x1		# could represent positions, offsets or ratios
        self.y1			= y1
        self.x2			= x2
        self.y2			= y2
        self.rotation		= rotation
        self.regions		= []

    def element( self ):
        return dict(
            name	= self.name,
            x1		= self.x1 * 25.4,       # always in mm
            y1		= self.y1 * 25.4,
            x2		= self.x2 * 25.4,
            y2		= self.y2 * 25.4,
            rotation	= self.rotation or 0.0
        )

    def __str__( self ):
        return f"({self.name:16}: ({float(self.x1):8}, {float( self.y1):8}) - ({float(self.x2):8} - {float(self.y2):8})"

    def add_region_relative( self, region ):
        region.x1	       += self.x1
        region.y1	       += self.y1
        region.x2	       += self.x2
        region.y2	       += self.y2
        self.regions.append( region )
        return region

    def add_region_proportional( self, region ):
        region.x1		= self.x1 + ( self.x2 - self.x1 ) * region.x1
        region.y1		= self.y1 + ( self.y2 - self.y1 ) * region.y1
        region.x2		= self.x1 + ( self.x2 - self.x1 ) * region.x2
        region.y2		= self.y1 + ( self.y2 - self.y1 ) * region.y2
        self.regions.append( region )
        return region

    def dimensions( self ):
        return Coordinate( (self.x2 - self.x1) * 25.4, (self.y2 - self.y1) * 25.4 )

    def elements( self ):
        """Yield a sequence of { 'name': "...", 'x1': #,  ... }"""
        if self.__class__ != Region:
            yield self.element()
        for r in self.regions:
            for d in r.elements():
                yield d


fonts			= dict(
    sans	= 'helvetica',
    mono	= 'courier',
)


class Text( Region ):
    def __init__( self, *args, font=None, text=None, size=None, size_ratio=None, align=None,
                  **kwds ):
        self.font		= font
        self.text		= text
        self.size		= size
        self.size_ratio		= size_ratio or 2/3
        self.align		= align
        super().__init__( *args, **kwds )

    def element( self ):
        d			= super().element()
        d['type']		= 'T'
        d['font']		= fonts.get( self.font ) or self.font or fonts.get( 'sans' )
        line_height		= (self.y2 - self.y1) * 72      # points
        d['size']		= self.size or int( round( line_height * self.size_ratio ))
        if self.text:
            d['text']		= self.text
        if self.align:
            d['align']		= self.align
        return d


class Image( Region ):
    def __init__( self, *args, font=None, text=None, size=None, **kwds ):
        self.font		= font
        self.text		= text
        self.size		= None
        super().__init__( *args, **kwds )

    def element( self ):
        d			= super().element()
        d['type']		= 'I'
        return d


class Line( Region ):
    def emit( self, d, *args, **kwds ):
        d['type']		= 'L'
        super().emit( *args, **kwds )


class Box( Region ):
    def element( self ):
        d			= super().element()
        d['type']		= 'B'
        return d


Coordinate			= namedtuple( 'Coordinate', ('x', 'y') )

card_size			= Coordinate( y=2+1/4, x=3+3/8 )
card_margin			= 1/16

card				= Box( 'card', 0, 0, card_size.x, card_size.y )
card_interior			= card.add_region_relative(
    Region( 'card-interior', x1=+card_margin, y1=+card_margin, x2=-card_margin, y2=-card_margin )
)

card_top			= card_interior.add_region_proportional(
    Region( 'card-top', x1=0, y1=0, x2=1, y2=1/4 )
)
card_bottom			= card_interior.add_region_proportional(
    Region( 'card-bottom', x1=0, y1=1/4, x2=1, y2=1 )
)
card_mnemonics			= card_bottom.add_region_proportional(
    Region( 'card-mnemonics', x1=0, y1=0, x2=3/4, y2=1 )
)
card_qr				= card_bottom.add_region_proportional(
    Image( 'card-qr', x1=3/4, y1=0, x2=1, y2=1 )
)
card_qr.y2			= card_qr.y1 + (card_qr.x2 - card_qr.x1)  # make height same as width

card_top.add_region_proportional(
    Text( 'card-title', x1=0, y1=0, x2=1, y2=44/100 )
)
card_top.add_region_proportional(
    Text( 'card-requires', x1=0, y1=45/100, x2=1, y2=75/100, align='C' )
)
card_top.add_region_proportional(
    Text( 'card-ETH', x1=0, y1=75/100, x2=1, y2=100/100, align='R' )
)

rows,cols		= 7,3
for r in range( rows ):
    for c in range( cols ):
        card_mnemonics.add_region_proportional(
            Text( f"mnem-{c * rows + r}",
                  x1=c/cols, y1=r/rows, x2=(c+1)/cols, y2=(r+1)/rows,
                  font='mono', size_ratio=1/2 )
        )


def output(
    name: str,
    group_threshold: int,
    groups: Dict[str,Tuple[int,List[str]]],
    accounts: Dict[str, eth_account.Account],
):
    """Produces a PDF with a number of cards containing the provided slip39.Details."""
    size		= (3, 5)
    margin		= .25
    margin_mm		= margin * 25.4

    pdf				= FPDF(
        orientation	= 'L',
        unit		= 'in',
        format		= size,
    )
    pdf.set_margin( margin )

    tplpdf			= FPDF()
    tpl				= FlexTemplate( tplpdf, list( card.elements() ))

    group_reqs			= list(
        f"{g_nam}({g_of}/{len(g_mns)})" if g_of != len(g_mns) else f"{g_nam}({g_of})"
        for g_nam,(g_of,g_mns) in groups.items() )
    requires			= f"Need {group_threshold} of {', '.join(group_reqs)} to recover."

    # Obtain the first ETH path and account, and address QR code
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
            for line in f:
                log.info( line.strip() )

    card_dim			= card.dimensions()
    card_cols			= int(( tplpdf.epw - margin_mm * 2 ) // card_dim.x )
    card_rows			= int(( tplpdf.eph - margin_mm * 2 ) // card_dim.y )
    cards_pp			= card_rows * card_cols

    def card_page( num ):
        return int( num // cards_pp )

    def card_xy( num ):
        nth			= ( num % cards_pp )
        r			= nth // card_cols
        c			= nth % card_cols
        return Coordinate( margin_mm + c * card_dim.x, margin_mm + r * card_dim.y )

    assert qr, "At least one ETH account must be supplied"
    for g_num,(g_name,(g_of,g_mnems)) in enumerate( groups.items() ):
        log.info( f"{g_name}({g_of}/{len(g_mnems)}): {requires}" )
        for mn_num,mnem in enumerate( g_mnems ):
            eth			= f"ETH({path}): {acct.address}{'...' if len(accounts)>1 else ''}"
            if mn_num == 0 or card_page( mn_num ) > card_page( mn_num - 1 ):
                tplpdf.add_page()

            tpl['card-title']	= f"SLIP39 {g_name}({mn_num+1}/{len(g_mnems)}) for: {name}"
            tpl['card-requires'] = requires
            tpl['card-eth']	= eth
            tpl['card-qr']	= qr.get_image()

            for n,m in enumerate_mnemonic( mnem ).items():
                tpl[f"mnem-{n}"] = m
            offsetx,offsety	= card_xy( mn_num )
            tpl.render( offsetx=offsetx, offsety=offsety )

    return tplpdf,accounts


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
        require			= math.ceil( int( size ) / 2. )		# eg. default 2/4, 3/5
    return name,(int(require),int(size))
group_parser.RE			= re.compile( # noqa E305
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
    log_cfg['level']		= levelmap[args.verbose] if args.verbose in levelmap else logging.DEBUG
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
