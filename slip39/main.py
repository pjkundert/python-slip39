import argparse
import ast
import codecs

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

from .generate		import create, random_secret, enumerate_mnemonic
from .util		import log_cfg, log_level, input_secure
from .defaults		import (
    GROUPS, GROUP_THRESHOLD_RATIO, GROUP_REQUIRED_RATIO,
    PATH_ETH_DEFAULT,
    CARD, CARD_SIZES, PAGE_MARGIN, FONTS, PAPER,
    BITS, BITS_DEFAULT,
)
from .			import layout

log				= logging.getLogger( __package__ )


def output(
    name: str,
    group_threshold: int,
    groups: Dict[str,Tuple[int,List[str]]],
    accounts: Dict[str, eth_account.Account],
    card_format: str		= CARD,   # 'index' or '(<h>,<w>),<margin>'
    paper_format: str		= PAPER,  # 'Letter', ...
) -> Tuple[FPDF, Dict[str, eth_account.Account]]:
    """Produces a PDF, containing a number of cards containing the provided slip39.Details if
    card_format is not False, and pass through the supplied accounts."""

    # Deduce the card size
    try:
        (card_h,card_w),card_margin = CARD_SIZES[card_format.lower()]
    except KeyError:
        (card_h,card_w),card_margin = ast.literal_eval( card_format )
    card_size			= layout.Coordinate( y=card_h, x=card_w )

    # Compute how many cards per page.  Flip page portrait/landscape to match the cards'.  Use the length
    # of the first Group's first Mnemonic to determine the number of mnemonics on each card.
    num_mnemonics		= len( groups[next(iter(groups.keys()))][1][0].split() )
    card			= layout.card(  # converts to mm
        card_size, card_margin, num_mnemonics=num_mnemonics )
    card_dim			= card.dimensions()

    # Find the best PDF and orientation, by max of returned cards_pp (cards per page)
    page_margin_mm		= PAGE_MARGIN * 25.4
    cards_pp,orientation,pdf,page_xy = max(
        layout.pdf_layout( card_dim, page_margin_mm, orientation=orientation, paper_format=paper_format )
        for orientation in ('portrait', 'landscape')
    )
    log.debug( f"Page: {paper_format} {orientation} {pdf.epw:.8}mm w x {pdf.eph:.8}mm h w/ {page_margin_mm}mm margins,"
               f" Card: {card_format} {card_dim.x:.8}mm w x {card_dim.y:.8}mm h == {cards_pp} cards/page" )

    elements			= list( card.elements() )
    if log.isEnabledFor( logging.DEBUG ):
        log.debug( f"Card elements: {json.dumps( elements, indent=4)}" )
    tpl				= FlexTemplate( pdf, list( card.elements() ))

    group_reqs			= list(
        f"{g_nam}({g_of}/{len(g_mns)})" if g_of != len(g_mns) else f"{g_nam}({g_of})"
        for g_nam,(g_of,g_mns) in groups.items() )
    requires			= f"Recover w/ {group_threshold} of {len(group_reqs)} groups {', '.join(group_reqs[:4])}{'...' if len(group_reqs)>4 else ''}"

    # Obtain the first ETH path and account, and address QR code
    qr				= None
    for path,acct in accounts.items():
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

    assert qr, "At least one ETH account must be supplied"
    card_n			= 0
    page_n			= None
    for g_n,(g_name,(g_of,g_mnems)) in enumerate( groups.items() ):
        for mn_n,mnem in enumerate( g_mnems ):
            p,(offsetx,offsety)	= page_xy( card_n )
            if p != page_n:
                pdf.add_page()
                page_n		= p
            card_n	       += 1

            tpl['card-title']	= f"SLIP39 {g_name}({mn_n+1}/{len(g_mnems)}) for: {name}"
            tpl['card-requires'] = requires
            tpl['card-eth']	= f"ETH {path}: {acct.address}{'...' if len(accounts)>1 else ''}"
            tpl['card-qr']	= qr.get_image()
            tpl[f'card-g{g_n}']	= f"{g_name:5.5}..{mn_n+1}" if len(g_name) > 6 else f"{g_name} {mn_n+1}"

            for n,m in enumerate_mnemonic( mnem ).items():
                tpl[f"mnem-{n}"] = m

            tpl.render( offsetx=offsetx, offsety=offsety )

    return pdf,accounts


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
        # eg. default 2/4, 3/5
        require			= math.ceil( int( size ) * GROUP_REQUIRED_RATIO )
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
    ap.add_argument( '-q', '--quiet', action="count",
                     default=0,
                     help="Reduce logging output." )
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
                     help="Use the supplied 128-, 256- or 512-bit hex value as the secret seed; '-' reads it from stdin (eg. output from slip39.recover)" )
    ap.add_argument( '--bits',
                     default=None,  # Do not enforce default of 128-bit seeds
                     help=f"Ensure that the seed is of the specified bit length; {', '.join( map( str, BITS ))} supported." )
    ap.add_argument( '--passphrase',
                     default=None,
                     help="Encrypt the master secret w/ this passphrase, '-' reads it from stdin (default: None/'')" )
    ap.add_argument( '-c', '--card',
                     default=None,
                     help=f"Card size; {', '.join(CARD_SIZES.keys())} or '(<h>,<w>),<margin>' (default: {CARD})" )
    ap.add_argument( '--paper',
                     default=None,
                     help=f"Paper size (default: {PAPER})" )
    ap.add_argument( '--no-card', dest="card", action='store_false',
                     help="Disable PDF SLIP-39 mnemonic card output" )
    ap.add_argument( '--text', action='store_true',
                     default=None,
                     help="Enable textual SLIP-39 mnemonic output to stdout" )
    ap.add_argument( 'names', nargs="*",
                     help="Account names to produce")
    args			= ap.parse_args( argv )

    log_cfg['level']		= log_level( args.verbose - args.quiet )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    groups			= dict(
        group_parser( g )
        for g in args.group or GROUPS
    )
    group_threshold		= args.threshold or math.ceil( len( groups ) * GROUP_THRESHOLD_RATIO )

    bits_desired		= int( args.bits ) if args.bits else BITS_DEFAULT

    master_secret		= args.secret
    if master_secret:
        # Master secret seed supplied as hex
        if master_secret == '-':
            master_secret	= input_secure( 'Master secret hex: ', secret=True )
        else:
            log.warning( "It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input" )
        if master_secret.lower().startswith('0x'):
            master_secret	= master_secret[2:]
        master_secret		= codecs.decode( master_secret, 'hex_codec' )
    else:
        # Generate a random secret seed
        master_secret		= random_secret( bits_desired // 8 )
    master_secret_bits		= len( master_secret ) * 8
    if master_secret_bits not in BITS:
        raise ValueError( f"A {master_secret_bits}-bit master secret was supplied; One of {BITS!r} expected" )
    if args.bits and master_secret_bits != bits_desired:  # If a certain seed size specified, enforce
        raise ValueError( f"A {master_secret_bits}-bit master secret was supplied, but {bits_desired} bits was specified" )

    # Optional passphrase (utf-8 encoded bytes
    passphrase			= args.passphrase or ""
    if passphrase == '-':
        passphrase		= input_secure( 'Master seed passphrase: ', secret=True )
    elif passphrase:
        log.warning( "It is recommended to not use '-p|--passphrase <password>'; specify '-' to read from input" )

    # Generate each desired SLIP-39 wallet.  Supports --card (the default) and --text
    for name in args.names or [ "" ]:
        details			= create(
            name		= name,
            group_threshold	= group_threshold,
            groups		= groups,
            master_secret	= master_secret,
            passphrase		= passphrase.encode( 'utf-8' ),
            paths		= args.path,
        )
        for path,account in details.accounts.items():
            log.error( f"ETH {path:20}: {account.address}" )

        if args.text:
            # Output the SLIP-39 mnemonics as text:
            #    name: mnemonic
            for g_name,(g_of,g_mnems) in details.groups.items():
                for mnem in g_mnems:
                    print( f"{name}{name and ': ' or ''}{mnem}" )

        # Unless --no-card specified, output a PDF containing the SLIP-39 mnemonic recovery cards
        pdf,accounts		= None,details.accounts
        if args.card is not False:
            pdf,_		= output(
                *details,
                card_format	= args.card or CARD,
                paper_format	= args.paper or PAPER )

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
        if not pdf_name.lower().endswith( '.pdf' ):
            pdf_name	       += '.pdf'

        if args.json:
            # If -j|--json supplied, also emit the encrypted JSON wallet.  This may be a *different*
            # password than the SLIP-39 master secret encryption passphrase.  It will be required to
            # decrypt and use the saved JSON wallet file, eg. to load a software Ethereum wallet.
            if args.json == '-':
                json_pwd	= input_secure( 'JSON key file password: ', secret=True )
            else:
                json_pwd	= args.json
                log.warning( "It is recommended to not use '-j|--json <password>'; specify '-' to read from input" )

            for path,account in accounts.items():
                json_str	= json.dumps( eth_account.Account.encrypt( account.key, json_pwd ), indent=4 )
                json_name	= pdf_name[:]
                if json_name.lower().endswith( '.pdf' ):
                    json_name	= json_name[:-4]
                json_name      += '.json'
                while os.path.exists( json_name ):
                    log.error( "ERROR: Will NOT overwrite {json_name}; adding '.new'!" )
                    json_name.append( '.new' )
                with open( json_name, 'w' ) as json_f:
                    json_f.write( json_str )
                log.warning( f"Wrote JSON encrypted wallet for {name!r} to: {json_name}" )

                if pdf:
                    # Add the encrypted JSON account recovery to the PDF also, if generated.
                    pdf.add_page()
                    margin_mm	= PAGE_MARGIN * 25.4
                    pdf.set_margin( 1.0 * 25.4 )

                    col_width	= pdf.epw - 2 * margin_mm
                    pdf.set_font( FONTS['sans'], size=10 )
                    line_height	= pdf.font_size * 1.2
                    pdf.cell( col_width, line_height, json_name )
                    pdf.ln( line_height )

                    pdf.set_font( FONTS['sans'], size=9 )
                    line_height	= pdf.font_size * 1.1

                    for line in json_str.split( '\n' ):
                        pdf.cell( col_width, line_height, line )
                        pdf.ln( line_height )
                    pdf.image( qrcode.make( json_str ).get_image(), h=min(pdf.eph, pdf.epw)/2, w=min(pdf.eph, pdf.epw)/2 )

        if pdf:
            pdf.output( pdf_name )
            log.warning( f"Wrote SLIP39-encoded wallet for {name!r} to: {pdf_name}" )

    return 0
