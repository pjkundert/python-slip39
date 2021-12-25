import argparse
import codecs
import getpass
import io
import json
import logging
import math
import os
import re

from datetime		import datetime
from typing		import Dict, List, Tuple

import qrcode
import eth_account
from fpdf		import FPDF, FlexTemplate

from .generate		import create, PATH_ETH_DEFAULT
from .util		import log_cfg
from .layout		import card, fonts, Coordinate

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
            log.info( f"  {mnem}" )
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
                     help="Output PDF to file or '-' (stdout); formatting w/ name, date, time, path and address allowed" )
    ap.add_argument( '-t', '--threshold',
                     default=None,
                     help="Number of groups required for recovery (default: half of groups, rounded up)" )
    ap.add_argument( '-g', '--group', action='append',
                     help="A group name[[<require>/]<size>] (default: <size> = 1, <require> = half of <size>, rounded up, eg. 'Fren(3/5)' )." )
    ap.add_argument( '-p', '--path', action='append',
                     help=f"A derivation path (default: {PATH_ETH_DEFAULT})" )
    ap.add_argument( '-j', '--json',
                     default=None,
                     help="Save an encrypted JSON wallet for each Ethereum address w/ this password, '-' reads it from stdin (default: None)" )
    ap.add_argument( '-s', '--secret',
                     default=None,
                     help="Use the supplied 128-bit hex value as the master secret seed (eg. from slip39.recover)" )
    ap.add_argument( '--passphrase',
                     default=None,
                     help="Encrypt the master secret w/ this passphrase, '-' reads it from stdin (default: None/'')" )
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

    # Optional passphrase (utf-8 encoded bytes
    passphrase			= args.passphrase or ""
    if passphrase == '-':
        passphrase		= getpass.getpass( 'Master seed passphrase: ' )
    elif passphrase:
        log.warning( "It is recommended to not use '-p|--passphrase <password>'; specify '-' to read from input" )

    # Master secret seed supplied as hex
    master_secret		= args.secret
    if master_secret:
        if master_secret.lower().startswith('0x'):
            master_secret	= master_secret[2:]
        master_secret		= codecs.decode( master_secret, 'hex_codec' )
        len_bits		= len( master_secret ) * 8
        if len_bits != 128:
            raise ValueError( f"A {len_bits}-bit master secret was supplied; 128 bits expected" )

    # Generate each desired SLIP-39 wallet
    for name in args.names or [ "" ]:
        pdf,accounts		= output(
            *create(
                name		= name,
                group_threshold = group_threshold,
                groups		= groups,
                master_secret	= master_secret,
                passphrase	= passphrase.encode( 'utf-8' ),
                paths	= args.path,
            )
        )
        now			= datetime.now()
        path			= next(iter(accounts.keys()))
        address			= accounts[path].address
        pdf_name		= args.output.format(
            name	= name or "SLIP39",
            date	= datetime.strftime( now, '%Y-%m-%d' ),
            time	= datetime.strftime( now, '%H.%M.%S'),
            path	= path,
            address	= address,
        )

        if args.json:
            # If -j|--json supplied, also emit the encrypted JSON wallet.  This may be a *different*
            # password than the SLIP-39 master secret encryption passphrase.  It will be required to
            # decrypt and use the saved JSON wallet file, eg. to load a software Ethereum wallet.
            if args.json == '-':
                json_pwd	= getpass.getpass( 'JSON key file password: ' )
            else:
                json_pwd	= args.json
                log.warning( "It is recommended to not use '-j|--json <password>'; specify '-' to read from input" )

            for path,account in accounts.items():
                json_str	= json.dumps( eth_account.Account.encrypt( account.key, json_pwd ), indent=4 )
                json_name	= args.output.format(
                    name	= name or "SLIP39",
                    date	= datetime.strftime( now, '%Y-%m-%d' ),
                    time	= datetime.strftime( now, '%H.%M.%S'),
                    path	= path,
                    address	= address,
                )
                if json_name.lower().endswith( '.pdf' ):
                    json_name	= json_name[:-4]
                json_name      += '.json'
                while os.path.exists( json_name ):
                    log.error( "ERROR: Will NOT overwrite {json_name}; adding '.new'!" )
                    json_name.append( '.new' )
                with open( json_name, 'w' ) as json_f:
                    json_f.write( json_str )
                log.warning( f"Wrote JSON encrypted wallet for {name!r} to: {json_name}" )

                # Add the encrypted JSON account recovery to the PDF also.
                pdf.add_page()
                margin_mm	= 1.0 * 25.4
                pdf.set_margin( 1.0 * 25.4 )

                col_width	= pdf.epw - 2 * margin_mm
                pdf.set_font( fonts['sans'], size=12 )
                line_height	= pdf.font_size * 1.25
                pdf.cell( col_width, line_height, json_name )
                pdf.ln( line_height )

                pdf.set_font( fonts['sans'], size=10 )
                line_height	= pdf.font_size * 1.25

                for line in json_str.split( '\n' ):
                    pdf.cell( col_width, line_height, line )
                    pdf.ln( line_height )
                pdf.image( qrcode.make( json_str ).get_image(), h=pdf.epw/2, w=pdf.epw/2 )

        pdf.output( pdf_name )
        log.warning( f"Wrote SLIP39-encoded wallet for {name!r} to: {pdf_name}" )

    return 0
