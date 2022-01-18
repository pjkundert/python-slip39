import argparse
import codecs
import json
import logging
import math
import os

from datetime		import datetime

import qrcode

from .api		import create, random_secret, group_parser
from .util		import log_cfg, log_level, input_secure
from .layout		import output_pdf
from .types		import Account
from .defaults		import (
    GROUPS, GROUP_THRESHOLD_RATIO,
    CARD, CARD_SIZES, PAGE_MARGIN, FONTS, PAPER,
    BITS, BITS_DEFAULT,
)

# Optionally support output of encrypted JSON files
eth_account			= None
try:
    import eth_account
except ImportError:
    pass


log				= logging.getLogger( __package__ )


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
                     default="{name}-{date}+{time}-{crypto}-{address}.pdf",
                     help="Output PDF to file or '-' (stdout); formatting w/ name, date, time, crypto, path and address allowed" )
    ap.add_argument( '-t', '--threshold',
                     default=None,
                     help="Number of groups required for recovery (default: half of groups, rounded up)" )
    ap.add_argument( '-g', '--group', action='append',
                     help="A group name[[<require>/]<size>] (default: <size> = 1, <require> = half of <size>, rounded up, eg. 'Fren(3/5)' )." )
    ap.add_argument( '-f', '--format', action='append',
                     default=[],
                     help=f"Specify default crypto address formats: {', '.join( Account.FORMATS )}; default {', '.join( f'{c}:{Account.address_format(c)}' for c in Account.CRYPTOCURRENCIES)}" )
    ap.add_argument( '-c', '--cryptocurrency', action='append',
                     default=[],
                     help=f"A crypto name and optional derivation path ('../<range>/<range>' allowed); defaults: {', '.join( f'{c}:{Account.path_default(c)}' for c in Account.CRYPTOCURRENCIES)}" )
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
    ap.add_argument( '-C', '--card',
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

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    log_cfg['level']		= log_level( args.verbose - args.quiet )
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    # If any --format <crypto>:<format> address formats provided
    for cf in args.format:
        try:
            Account.address_format( *cf.split( ':' ) )
        except Exception as exc:
            log.error( f"Invalid address format: {cf}: {exc}" )
            raise

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

    # Optional passphrase
    passphrase			= args.passphrase or ""
    if passphrase == '-':
        passphrase		= input_secure( 'Master seed passphrase: ', secret=True )
    elif passphrase:
        log.warning( "It is recommended to not use '-p|--passphrase <password>'; specify '-' to read from input" )

    cryptopaths			= []
    for crypto in args.cryptocurrency or ['ETH', 'BTC']:
        try:
            crypto,paths	= crypto.split( ':' )
        except ValueError:
            crypto,paths	= crypto,None
        cryptopaths.append( (crypto,paths) )

    # Generate each desired SLIP-39 wallet.  Supports --card (the default)
    for name in args.names or [ "" ]:
        details			= create(
            name		= name,
            group_threshold	= group_threshold,
            groups		= groups,
            master_secret	= master_secret,
            passphrase		= passphrase.encode( 'utf-8' ),
            cryptopaths		= cryptopaths,
        )
        # Get the first group of the accountgroups in details.accounts.  Must be
        accounts		= details.accounts
        assert accounts and accounts[0], \
            "At least one --cryptocurrency must be specified"
        for account in accounts[0]:
            log.warning( f"{account.crypto:6} {account.path:20}: {account.address}" )

        if args.text:
            # Output the SLIP-39 mnemonics as text:
            #    name: mnemonic
            for g_name,(g_of,g_mnems) in details.groups.items():
                for mnem in g_mnems:
                    print( f"{name}{name and ': ' or ''}{mnem}" )

        # Unless --no-card specified, output a PDF containing the SLIP-39 mnemonic recovery cards
        pdf			= None
        if args.card is not False:
            pdf,_		= output_pdf(
                *details,
                card_format	= args.card or CARD,
                paper_format	= args.paper or PAPER )

        now			= datetime.now()

        pdf_name		= args.output.format(
            name	= name or "SLIP39",
            date	= datetime.strftime( now, '%Y-%m-%d' ),
            time	= datetime.strftime( now, '%H.%M.%S'),
            crypto	= accounts[0][0].crypto,
            path	= accounts[0][0].path,
            address	= accounts[0][0].address,
        )
        if not pdf_name.lower().endswith( '.pdf' ):
            pdf_name	       += '.pdf'

        if args.json:
            # If -j|--json supplied, also emit the encrypted JSON wallet.  This may be a *different*
            # password than the SLIP-39 master secret encryption passphrase.  It will be required to
            # decrypt and use the saved JSON wallet file, eg. to load a software Ethereum wallet.
            assert eth_account, \
                "The optional eth-account package is required to support output of encrypted JSON wallets\n" \
                "    python3 -m pip install eth-account"
            assert any( 'ETH' == crypto for crypto,paths in cryptopaths ), \
                "--json is only valid if '--crypto ETH' wallets are specified"
            if args.json == '-':
                json_pwd	= input_secure( 'JSON key file password: ', secret=True )
            else:
                json_pwd	= args.json
                log.warning( "It is recommended to not use '-j|--json <password>'; specify '-' to read from input" )

            for eth in (
                account
                for group in accounts
                for account in group
                if account.crypto == 'ETH'
            ):
                json_str	= json.dumps( eth_account.Account.encrypt( eth.key, json_pwd ), indent=4 )
                json_name	= args.output.format(
                    name	= name or "SLIP39",
                    date	= datetime.strftime( now, '%Y-%m-%d' ),
                    time	= datetime.strftime( now, '%H.%M.%S'),
                    crypto	= eth.crypto,
                    path	= eth.path,
                    address	= eth.address,
                )
                if json_name.lower().endswith( '.pdf' ):
                    json_name	= json_name[:-4]
                json_name      += '.json'
                while os.path.exists( json_name ):
                    log.error( "ERROR: Will NOT overwrite {json_name}; adding '.new'!" )
                    json_name  += '.new'
                with open( json_name, 'w' ) as json_f:
                    json_f.write( json_str )
                log.warning( f"Wrote JSON {name or 'SLIP39'}'s encrypted ETH wallet {eth.address} derived at {eth.path} to: {json_name}" )

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
