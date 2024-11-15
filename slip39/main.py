
#
# Python-slip39 -- Ethereum SLIP-39 Account Generation and Recovery
#
# Copyright (c) 2022, Dominion Research & Development Corp.
#
# Python-slip39 is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.  It is also available under alternative (eg. Commercial) licenses, at
# your option.  See the LICENSE file at the top of the source tree.
#
# Python-slip39 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#

from __future__		import annotations

import argparse
import codecs
import logging

import tabulate

from .			import Account
from .api		import random_secret, stretch_seed_entropy
from .util		import log_cfg, log_level, input_secure
from .layout		import write_pdfs
from .defaults		import (   # noqa: F401
    CARD, CARD_SIZES, PAPER, WALLET, WALLET_SIZES,
    BITS, BITS_DEFAULT,
    FILENAME_FORMAT,
    FILENAME_KEYWORDS,
    CRYPTO_PATHS,
)

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( __package__ )


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Create and output SLIP-39 encoded Seeds and Paper Wallets to a PDF file.",
        epilog = "" )
    ap.add_argument( '-v', '--verbose', action="count",
                     default=0,
                     help="Display logging information." )
    ap.add_argument( '-q', '--quiet', action="count",
                     default=0,
                     help="Reduce logging output." )
    ap.add_argument( '-o', '--output',
                     default=FILENAME_FORMAT,
                     help=f"Output PDF to file or '-' (stdout: use -q!); formatting w/ {', '.join( FILENAME_KEYWORDS )} allowed" )
    ap.add_argument( '-t', '--threshold',
                     default=None,
                     help="Number of groups required for recovery (default: half of groups, rounded up)" )
    ap.add_argument( '-g', '--group', action='append',
                     help="A group name[[<require>/]<size>] (default: <size> = 1, <require> = half of <size>, rounded up, eg. 'Frens(3/5)' )." )
    ap.add_argument( '-f', '--format', action='append',
                     default=[],
                     help=f"Specify crypto address formats: {', '.join( Account.FORMATS )}; default: " + ', '.join(
                         f'{c}:{Account.address_format(c)}' for c in Account.CRYPTO_NAMES.values()
                     ))
    ap.add_argument( '-c', '--cryptocurrency', action='append',
                     default=[],
                     help="A crypto name and optional derivation path (eg. '../<range>/<range>'); defaults: " + ', '.join(
                         f"{c}:{Account.path_default(c)}" for c in Account.CRYPTO_NAMES.values()
                     ))
    ap.add_argument( '-p', '--path',
                     default=None,
                     help="Modify all derivation paths by replacing the final segment(s) w/ the supplied range(s), eg. '.../1/-' means .../1/[0,...)")
    ap.add_argument( '-j', '--json',
                     default=None,
                     help="Save an encrypted JSON wallet for each Ethereum address w/ this password, '-' reads it from stdin (default: None)" )
    ap.add_argument( '-w', '--wallet',
                     default=None,
                     help="Produce paper wallets in output PDF; each wallet private key is encrypted this password (use --wallet=\"\" for empty password)" )
    ap.add_argument( '--wallet-hint',
                     default=None,
                     help="Paper wallets password hint" )
    ap.add_argument( '--wallet-format',
                     default=None,
                     help=f"Paper wallet size; {', '.join(WALLET_SIZES.keys())} or '(<h>,<w>),<margin>' (default: {WALLET})" )
    ap.add_argument( '-s', '--secret',
                     default=None,
                     help="Use the supplied BIP-39 Mnemonic or 128-, 256- or 512-bit hex value as the secret seed; '-' reads it from stdin (eg. output from slip39.recover)" )
    ap.add_argument( '-e', '--entropy',
                     default=None,
                     help="Additional entropy; if 0x... hex, used directly; otherwise, UTF-8 stretched via SHA-512" )
    ap.add_argument( '--show', action='store_true',
                     default=False,
                     help="Show derivation of master seed" )
    ap.add_argument( '--no-show', dest="show", action='store_false',
                     help="Disable showing derivation of master seed" )
    ap.add_argument( '--bits',
                     default=None,  # Do not enforce default of 128-bit seeds
                     help=f"Ensure that the seed is of the specified bit length; {', '.join( map( str, BITS ))} supported." )
    ap.add_argument( '--using-bip39', action='store_true',
                     default=None,
                     help="Generate Seed from secret Entropy using BIP-39 generation algorithm (encode as BIP-39 Mnemonics, encrypted using --passphrase)" )
    ap.add_argument( '--passphrase',
                     default=None,
                     help="Encrypt the master secret w/ this passphrase, '-' reads it from stdin (default: None/'')" )
    ap.add_argument( '-C', '--card',
                     default=None,
                     help=f"Card size; {', '.join(CARD_SIZES.keys())} or '(<h>,<w>),<margin>' (default: {CARD})" )
    ap.add_argument( '--no-card', dest="card", action='store_false',
                     help="Disable PDF SLIP-39 mnemonic card output" )
    ap.add_argument( '--paper',
                     default=None,
                     help=f"Paper size (default: {PAPER})" )
    ap.add_argument( '--cover', dest="cover_page", action='store_true',
                     default=True,
                     help="Produce PDF SLIP-39 cover page" )
    ap.add_argument( '--no-cover', dest="cover_page", action='store_false',
                     help="Disable PDF SLIP-39 cover page" )
    ap.add_argument( '--text', action='store_true',
                     default=None,
                     help="Enable textual SLIP-39 mnemonic output to stdout" )
    ap.add_argument( '--watermark',
                     default=None,
                     help="Include a watermark on the output SLIP-39 mnemonic cards" )
    ap.add_argument( '--double-sided', action='store_true',
                     default=None,
                     help="Enable double-sided PDF (default)" )
    ap.add_argument( '--no-double-sided', dest="double_sided", action='store_false',
                     help="Disable double-sided PDF" )
    ap.add_argument( '--single-sided', dest="double_sided", action='store_false',
                     help="Enable single-sided PDF" )
    ap.add_argument( 'names', nargs="*",
                     help="Account names to produce; if --secret Entropy is supplied, only one is allowed.")
    args			= ap.parse_args( argv )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    log_cfg['level']		= log_level( args.verbose - args.quiet )
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    # Confirm sanity of args
    log.debug( f"args: {args!r}" )
    if args.path:
        assert args.path.startswith( 'm/' ) or ( args.path.startswith( '..' ) and args.path.lstrip( '.' ).startswith( '/' )), \
            "A --path must start with 'm/', or '../', indicating intent to replace 1 or more trailing components of each cryptocurrency's derivation path"

    # If any --format <crypto>:<format> address formats provided
    for cf in args.format:
        try:
            Account.address_format( *cf.split( ':' ) )
        except Exception as exc:
            log.error( f"Invalid address format: {cf}: {exc}" )
            raise

    bits_desired		= int( args.bits ) if args.bits else BITS_DEFAULT

    # Master Secret Seed data.  Either raw hex [0x]0123.., or a BIP-39 Mnemonic phrase.  If raw hex,
    # we'll also support adding additional entropy (either more raw hex from some external entropy
    # source, or UTF-8 data such as dice rolls, etc. which we'll stretch using SHA-512).
    master_secret		= args.secret
    if master_secret:
        # Master secret seed may be supplied as hex or a BIP-39 Mnemonic (leave as str)
        if master_secret == '-':
            master_secret	= input_secure( 'Master secret (hex or BIP-39): ', secret=True )
        else:
            log.warning( "It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input" )
        if master_secret.lower().startswith('0x'):
            master_secret	= master_secret[2:]
        if all( c in "0123456789abcdef" for c in master_secret.lower() ):
            master_secret	= codecs.decode( master_secret, 'hex_codec' )
    else:
        # Generate a random secret seed, as bytes
        master_secret		= random_secret( bits_desired // 8 )

    # Process Master Secret + Entropy into seed.  For practice runs (with -v[v]), show the contents and
    show_table			= []
    if isinstance( master_secret, bytes ):
        master_secret_bits		= len( master_secret ) * 8
        if master_secret_bits not in BITS:
            raise ValueError( f"A {master_secret_bits}-bit master secret was supplied; One of {BITS!r} expected" )
        if args.bits and master_secret_bits != bits_desired:  # If a certain seed size specified, enforce
            raise ValueError( f"A {master_secret_bits}-bit master secret was supplied, but {bits_desired} bits was specified" )
        if args.entropy:
            args.show and show_table.append( [ "Input Secret:", f"0x{master_secret.hex()}", "From supplied hex data" ] )
            if args.entropy.lower().startswith('0x'):
                entropy		= stretch_seed_entropy( args.entropy[2:], 0, master_secret_bits, 'hex_codec' )
                args.show and show_table.append( [ "xor Entropy:", f"0x{entropy.hex()}", "From supplied hex data" ] )
            else:
                entropy		= stretch_seed_entropy( args.entropy, 0, master_secret_bits, 'UTF-8' )
                args.show and show_table.append( ["xor Entropy:", f"0x{entropy.hex()}", f"From SHA-512(\"{args.entropy}\")" ] )
            master_secret	= bytes( d ^ e for d,e in zip( master_secret, entropy ) )
            args.show and show_table.append( tabulate.SEPARATING_LINE )
        args.show and show_table.append( [ "Master Seed:", f"0x{master_secret.hex()}", f"Using {'BIP' if args.using_bip39 else 'SLIP'}-39 derivation" ] )
    else:
        assert not args.entropy, "No additional entropy supported for BIP-39 master secret"
        args.show and show_table.append( [ "Master Seed:", master_secret, "(Using BIP-39 derivation)" ] )
    args.show and print( tabulate.tabulate( show_table, headers=("Description", "Seed data", "Interpretation"), tablefmt='orgtbl' ))

    # SLIP-39 Passphrase.  This is not recommended, as A) it is another thing that must be saved in
    # addition to the SLIP-39 Mnemonics in order to recover the Seed, and B) it is not implemented
    # by the Trezor hardware wallet.  Also used for --bip39, where the wallets are produced from the
    # master_secret Entropy using BIP-39 standard Seed generation.
    passphrase			= args.passphrase or ""
    if passphrase == '-':
        passphrase		= input_secure( 'Master seed passphrase: ', secret=True )
    elif passphrase:
        log.warning( "It is recommended to not use '-p|--passphrase <password>'; specify '-' to read from input" )
    if passphrase:
        if args.using_bip39 or isinstance( master_secret, str ):
            log.warning( "The BIP-39 Passphrase will be used only for deducing Crypto addresses; you must remember it, for BIP-39 wallet recovery" )
        else:
            log.warning( "The SLIP-39 Standard Passphrase is not compatible w/ the Trezor hardware wallet; use its 'Hidden wallet' feature instead" )

    # Optional Paper Wallet and/or JSON Wallet file passwords
    wallet_pwd			= args.wallet
    if wallet_pwd:
        if wallet_pwd == '-':
            wallet_pwd		= input_secure( 'Paper Wallet password: ', secret=True )
        else:
            log.warning( "It is recommended to not use '-w|--wallet <password>'; specify '-' to read from input" )
    wallet_pwd_hint		= args.wallet_hint
    wallet_format		= args.wallet_format

    json_pwd			= args.json
    if json_pwd is not None:
        if json_pwd == '-':
            json_pwd		= input_secure( 'Ethereum JSON wallet file password: ', secret=True )
        else:
            log.warning( "It is recommended to not use '-j|--json <password>'; specify '-' to read from input" )

    try:
        # Output the filenames of the emitted PDFs (the keys of the returned dict), one per line
        # (unless quiet, or --no-card)
        results			= write_pdfs(
            names		= args.names,
            master_secret	= master_secret,
            passphrase		= passphrase,
            using_bip39		= args.using_bip39,
            group		= args.group,
            group_threshold	= args.threshold,
            cryptocurrency	= args.cryptocurrency,
            edit		= args.path,
            card_format		= args.card,    # False inhibits SLIP-39 Card output
            paper_format	= args.paper,
            filename		= args.output,  # outputs to the current working dir, by default
            json_pwd		= json_pwd,
            text		= args.text,
            wallet_pwd		= wallet_pwd,
            wallet_pwd_hint	= wallet_pwd_hint,
            wallet_format	= wallet_format,
            cover_page		= args.cover_page,
            watermark		= args.watermark,
            double_sided	= args.double_sided,
        )
        if args.card is not False and (args.verbose - args.quiet) >= 0:
            print( "\n".join( results ))
    except Exception as exc:
        log.exception( f"Failed to write PDFs: {exc}" )
        return 1
    return 0
