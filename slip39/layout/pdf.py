
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

import ast
import io
import json
import logging
import math
import os
import warnings

from datetime		import datetime
from collections.abc	import Callable
from pathlib		import Path
from typing		import Dict, List, Tuple, Optional, Sequence, Any

import qrcode
import fpdf		# FPDF, FlexTemplate, FPDF_FONT_DIR

from ..api		import Account, cryptopaths_parser, create, enumerate_mnemonic, group_parser
from ..util		import chunker
from ..recovery		import recover, produce_bip39
from ..defaults		import (
    FONTS, CARD, CARD_SIZES, PAPER, PAGE_MARGIN, MM_IN, PT_IN,
    WALLET, WALLET_SIZES,
    GROUPS, GROUP_THRESHOLD_RATIO,
    FILENAME_FORMAT,
)
from .components	import (
    Coordinate, Region, Box, Image, Text,
    layout_components, layout_card, layout_wallet,
)
from .printer		import (
    printer_output,
)


# Optionally support output of encrypted JSON files
eth_account			= None
try:
    import eth_account
except ImportError:
    pass

log				= logging.getLogger( __package__ )


class FPDF_Autoload_Fonts( fpdf.FPDF ):
    """If attempting to set an unknown font, tries to load it. """
    def __init__( self, *args, font_dir=None, **kwds ):
        self.font_dir		= font_dir
        if self.font_dir is None:
            self.font_dir	= font_dir if font_dir is not None else Path( __file__ ).resolve().parent / "font"
        return super().__init__( *args, **kwds )

    def set_font( self, family=None, style="", size=0 ):
        # Deduce a set of lists of features synonyms, and expected fontkey
        feature_suffixes	= dict(
            B	= ( 'bold', ),
            I	= ( 'italic', 'oblique' ),      # Typical aliases seen
            U	= (),				# Ignored for font loading purposes
        )

        assert all( c in feature_suffixes for c in style ), \
            f"Unrecognized font style in {style!r}"
        features		= set( feature_suffixes[c] for c in style )
        if not features:
            features.add( ( 'regular', ) )
        family			= family.lower()
        fontkey			= family + style

        try:
            return super().set_font( family=family, style=style, size=size )
        except fpdf.FPDFException as exc:
            if "Undefined font" not in str( exc ):
                raise
            log.info( f"Loading custom font {fontkey}: {exc}" )

        # Search for the *shortest* fname that matches the requested family/features.  A font with
        # no features suffix will be assumed to have the -Regular suffix.
        fname_best		= None
        for fname in sorted( self.font_dir.glob( '*.ttf' ) ):
            log.debug( f"Evaluating {family=} + {features=} against:  {fname}" )
            # Eg "DejaVuSansMono-BoldOblique.ttf" --> "dejavusansmono", "boldoblique"
            fname_segments	= fname.stem.split( '-', 2 )		# the file name w/o path or suffix
            fname_family	= fname_segments[0].lower()
            fname_features 	= ''.join( fname_segments[1:] ).lower() or 'regular'
            if family not in fname_family:
                continue
            # Family matches; now, verify that the features eg. Italic/Oblique, Bold, Regular are in
            # the fname_features.
            for feature in features:
                if not any( synomym in fname_features for synomym in feature ):
                    break
            else:
                # Every one of features specified (or one of the feature's synonyms) appeared in
                # this fname's feature segment.  It is a candidate; is it better (shorter) than the
                # one currently found?  Eg. Font-Bold.ttf better than Font-Oblique.ttf, if no
                # Font.ttf or Font-Regular.ttf
                if fname_best is None or len( fname.stem ) < len( fname_best.stem ):
                    log.debug( f"Font named {family=} + {features=} matching: {fname} and better than {fname_best}" )
                    fname_best	= fname
                else:
                    log.debug( f"Font named {family=} + {features=} matching: {fname}, but worse than  {fname_best}" )
                continue
            log.debug( f"Font named {family=} + {features=} no match: {fname}" )
        if fname_best:
            log.info( f"Font named {family=} + {features=} loading:  {fname_best} (as '{family}{style}')" )
            self.add_font( family=family, style=style, fname=str( fname_best ))
        else:
            log.warning( f"Font name {family=} and {features=} not found for: {fontkey}" )
            raise fpdf.FPDFException( f"TTF Font file not found for: {fontkey}" )

        return super().set_font( family=family, style=style, size=size )


def layout_pdf(
        card_dim: Coordinate,                   # mm.
        page_margin_mm: float	= .25 * MM_IN,  # 1/4" in mm.
        orientation: str	= 'portrait',
        paper_format: Any	= PAPER,        # Can be a paper name (Letter) or (x, y) dimensions in mm.
        font_dir: Optional[Path] = None,
) -> Tuple[int, str, Callable[[int],[int, Coordinate]], fpdf.FPDF]:
    """Find the ideal orientation for the most cards of the given dimensions.  Returns the number of
    cards per page, the FPDF, and a function useful for laying out templates on the pages of the
    PDF."""
    pdf				= FPDF_Autoload_Fonts(
        orientation	= orientation,
        format		= paper_format,
    )
    pdf.set_margin( 0 )

    cards_pp,page_xy		= layout_components(
        pdf, comp_dim=card_dim, page_margin_mm=page_margin_mm
    )
    return cards_pp, orientation, page_xy, pdf


def output_pdf( *args, **kwds ):
    warnings.warn(
        "output_pdf() is deprecated; use produce_pdf instead.",
        PendingDeprecationWarning,
    )
    _,pdf,accounts		= produce_pdf( *args, **kwds )
    return pdf,accounts


def produce_pdf(
    name: str,
    group_threshold: int,			# SLIP-39 Group Threshold required
    groups: Dict[str,Tuple[int,List[str]]],     # SLIP-39 Groups {<name>: (<need>,[<mnemonic>,...])
    accounts: Sequence[Sequence[Account]],      # The crypto account(s); at least 1 of each required
    using_bip39: bool,				# Using BIP-39 wallets Seed generation
    card_format: str		= CARD,		# 'index' or '(<h>,<w>),<margin>'
    paper_format: Any		= None,		# 'Letter', (x,y) dimensions in mm.
    orientations: Sequence[str]	= None,		# available orientations; default portrait, landscape
    cover_text: Optional[str]	= None,		# Any Cover Page text; we'll append BIP-39 if 'using_bip39'
    watermark: Optional[str]	= None,
) -> Tuple[Tuple[str,str], fpdf.FPDF, Sequence[Sequence[Account]]]:
    """Produces an FPDF containing the specified SLIP-39 Mnemonics group recovery cards.

    Returns the required Paper description [<format>,<orientation>], the FPDF containing the
    produced cards, and the cryptocurrency accounts from the supplied slip39.Details.

    Makes available several fonts.
    """
    if paper_format is None:
        paper_format		= PAPER
    if orientations is None:
        orientations		= ('portrait', 'landscape')
    # Deduce the card size
    try:
        (card_h,card_w),card_margin = CARD_SIZES[card_format.lower()]
    except KeyError:
        (card_h,card_w),card_margin = ast.literal_eval( card_format )
    card_size			= Coordinate( y=card_h, x=card_w )

    # Compute how many cards per page.  Flip page portrait/landscape to match the cards'.  Use the length
    # of the first Group's first Mnemonic to determine the number of mnemonics on each card.
    num_mnemonics		= len( groups[next(iter(groups.keys()))][1][0].split() )
    card			= layout_card(  # converts to mm
        card_size, card_margin, num_mnemonics=num_mnemonics )
    card_dim			= card.mm()

    # Find the best PDF and orientation, by max of returned cards_pp (cards per page).  Assumes
    # layout_pdf returns a tuple that can be compared; cards_pp,orientation,... will always sort.
    page_margin_mm		= PAGE_MARGIN * MM_IN
    cards_pp,orientation,page_xy,pdf = max(
        layout_pdf( card_dim, page_margin_mm, orientation=orientation, paper_format=paper_format )
        for orientation in orientations
    )
    log.debug( f"Page: {paper_format} {orientation} {pdf.epw:.8}mm w x {pdf.eph:.8}mm h w/ {page_margin_mm}mm margins,"
               f" Card: {card_format} {card_dim.x:.8}mm w x {card_dim.y:.8}mm h == {cards_pp} cards/page" )

    card_elements		= list( card.elements() )
    if log.isEnabledFor( logging.DEBUG ):
        log.debug( f"Card elements: {json.dumps( card_elements, indent=4)}" )
    tpl				= fpdf.FlexTemplate( pdf, card_elements )

    group_reqs			= list(
        f"{g_nam}({g_of}/{len(g_mns)})" if g_of != len(g_mns) else f"{g_nam}({g_of})"
        for g_nam,(g_of,g_mns) in groups.items() )
    requires			= f"Recover w/ {group_threshold} of {len(group_reqs)} groups {', '.join(group_reqs[:4])}{'...' if len(group_reqs)>4 else ''}"

    # Convert all of the first group's account(s) to an address QR code
    assert accounts and accounts[0], \
        "At least one cryptocurrency account must be supplied"
    qr				= {}
    for i,acct in enumerate( accounts[0] ):
        qrc			= qrcode.QRCode(
            version	= None,
            error_correction = qrcode.constants.ERROR_CORRECT_M,
            box_size	= 10,
            border	= 1
        )
        qrc.add_data( acct.address )
        qrc.make( fit=True )

        qr[i]			= qrc.make_image()
        if log.isEnabledFor( logging.INFO ):
            f			= io.StringIO()
            qrc.print_ascii( out=f )
            f.seek( 0 )
            for line in f:
                log.info( line.strip() )

    if cover_text:
        # Cover page is always laid out in landscape, and rotated if necessary
        cvw			= max( pdf.epw, pdf.eph )
        cvh			= min( pdf.epw, pdf.eph )
        cover			= Region(
            'cover', 0, 0, cvw / MM_IN, cvh / MM_IN
        ).add_region_relative(
            Box( 'cover-interior', x1=+1/2, y1=+1/2, x2=-1/2, y2=-1/2 )
        )
        cover.add_region_proportional(
            Image( 'cover-image', x1=1/4, x2=3/4, y1=1/4, y2=3/4, priority=-3 )
        ).square().add_region(
            Image( 'cover-fade', priority=-2 )
        )
        cover.add_region_proportional(
            Text( 'cover-text', y2=1/45, font='mono', multiline=True )  # 1st line
        )
        cover.add_region_proportional(
            Region( 'cover-rhs', x1=3/5, y1=1/5 )  # On right, below full-width header
        ).add_region_proportional(
            Text( 'cover-sent', y2=1/25, font='mono', multiline=True )  # 1st line
        )

        cover_elements		= list( cover.elements() )
        if log.isEnabledFor( logging.DEBUG ):
            log.debug( f"Cover elements: {json.dumps( cover_elements, indent=4)}" )
        tpl_cover		= fpdf.FlexTemplate( pdf, cover_elements )
        images			= os.path.dirname( __file__ )
        tpl_cover['cover-image'] = os.path.join( images, 'SLIP-39.png' )
        tpl_cover['cover-fade'] = os.path.join( images, '1x1-ffffffbf.png' )

        slip39_mnems		= []
        slip39_group		= []
        g_nam_max		= max( map( len, groups.keys() ))
        for g_nam,(g_of,g_mns) in groups.items():
            slip39_mnems.extend( g_mns )
            slip39_group.append( f"{g_nam:{g_nam_max}}: {g_of} of {len(g_mns)} to recover" )
            slip39_group.extend( f"  {i+1:2}: ____________________" for i in range( len( g_mns )))
        if using_bip39:
            # Add the BIP-39 Mnemonics to the cover_text, by recovering the master_secret from the
            # SLIP-39 Mnemonics.
            master_secret	= recover( slip39_mnems )
            bip39_enum		= enumerate_mnemonic( produce_bip39( entropy=master_secret ) )
            rows		= ( len( bip39_enum ) + 4 ) // 5
            cols		= ( len( bip39_enum ) + rows - 1 ) // rows
            cover_text	       += "\n--------------8<-------------[ cut here ]------------------"
            cover_text	       += f"\n\n            Your {len(bip39_enum)}-word BIP-39 Seed Phrase is:\n"
            for r in range( rows ):
                cover_text     += "\n    "
                for c in range( cols ):
                    word	= bip39_enum.get( c * rows + r )
                    cover_text += f"{word or '':12}"
            cover_text	       += "\n"

        tpl_cover['cover-text']	= cover_text
        cover_sent		= "SLIP-39 Mnemonic Card Recipients:\n\n"
        cover_sent	       += "\n".join( slip39_group )
        tpl_cover['cover-sent']	= cover_sent

        pdf.add_page()
        if orientation.lower().startswith( 'p' ):
            tpl_cover.render( offsetx=pdf.epw, rotate=-90.0 )
        else:
            tpl_cover.render()

    card_n			= 0
    page_n			= None
    for g_n,(g_name,(g_of,g_mnems)) in enumerate( groups.items() ):
        for mn_n,mnem in enumerate( g_mnems ):
            p,(offsetx,offsety)	= page_xy( card_n )
            if p != page_n:
                pdf.add_page()
                page_n		= p
            card_n	       += 1

            tpl['card-title']	= f"{name} : {g_name}"
            if watermark:
                tpl['card-watermark'] = watermark
            for n,m in enumerate_mnemonic( mnem ).items():
                tpl[f"mnem-{n}"] = m

            tpl.render( offsetx=offsetx, offsety=offsety )

    return (paper_format,orientation),pdf,accounts


def write_pdfs(
    names		= None,		# sequence of [ <name>, ... ], or { "<name>": <details> }
    master_secret	= None,		# Derive SLIP-39 details from this seed (if not supplied in names)
    passphrase		= None,		# UTF-8 encoded passphrase; default is '' (empty)
    using_bip39		= False,        # Generate Seed from Entropy via BIP-39 generation algorithm
    group		= None,		# Group specifications, [ "Frens(3/6)", ... ]
    group_threshold	= None,		# int, or 1/2 of groups by default
    cryptocurrency	= None,		# sequence of [ 'ETH:<path>', ... ] to produce accounts for
    edit		= None,		# Adjust crypto paths according to the provided path edit
    card_format		= None,		# Eg. "credit"; False outputs no SLIP-39 Mnemonic cards to PDF
    paper_format	= None,		# Eg. "Letter", "Legal", (x,y)
    filename		= None,		# A file name format w/ {path}, etc. formatters
    filepath		= True,		# A file path, if PDF output to file is desired; ''/True implies current dir.
    printer		= None,		# A printer name (or True for default), if output to printer is desired
    json_pwd		= None,		# If JSON wallet output desired, supply password
    text		= None,		# Truthy outputs SLIP-39 recover phrases to stdout
    wallet_pwd		= None,		# If paper wallet images desired, supply password
    wallet_pwd_hint	= None,		# an optional password hint
    wallet_format	= None,		# and a paper wallet format (eg. 'quarter')
    wallet_paper	= None,		# default Wallets to output on Letter format paper,
    cover_page		= True,         # Produce a cover page (including BIP-39 Mnemonic, if using_bip39)
    watermark		= None,		# Any watermark desired on each output
):
    """Writes a PDF containing a unique SLIP-39 encoded Seed Entropy for each of the names specified.

    If a sequence of multiple 'names' are supplied, then no master_secret is allowed (we must
    generate for each name), or a dict of { 'name': <details>, ... } for each name must be provided
    (neither master_secret nor using_bip39 allowed).

    If we are generating master_secrets, and accounts, a number of Cryptocurrency wallet public
    addresses and QR codes are generated; optionally, 'using_bip39' to force BIP-39 standard Seed
    generation (instead of SLIP-39 standard, which uses the Seed Entropy directly).

    If 'using_bip39' and 'cover_page', the BIP-39 Mnemonic phrase card is also produced.  It is
    recommended to destroy this BIP-39 Mnemonic (ideally), or store it very, very securely (not
    recommended).  Use the SLIP-39 "Recover" Controls, instead, to recover the BIP-39 Mnemonic
    phrase when needed to restore a hardware wallet.

    Returns a { "<filename>": <details>, ... } dictionary of all PDF files written, and each of
    their account details.

    """
    # Convert sequence of group specifications into standard { "<group>": (<needs>, <size>) ... }
    if isinstance( group, dict ):
        groups			= group
    else:
        groups			= dict(
            group_parser( g )
            for g in group or GROUPS
        )
    assert groups and all( isinstance( k, str ) and len( v ) == 2 for k,v in groups.items() ), \
        f"Each group member specification must be a '<group>': (<needs>, <size>), not {type(next(groups.items()))}"

    group_threshold		= int( group_threshold ) if group_threshold else math.ceil( len( groups ) * GROUP_THRESHOLD_RATIO )

    cryptopaths			= cryptopaths_parser( cryptocurrency, edit=edit )

    # If account details not provided in names, generate them.  If using_bip39 is specified, this is
    # where we use BIP-39 Seed generation to produce the wallet Seed, instead of SLIP-39 which uses
    # the entropy directly (optionally, with a passphrase, which is not typically done, and isn't
    # Trezor compatible).
    if not isinstance( names, dict ):
        assert not master_secret or not names or len( names ) == 1, \
            "Creating multiple account details from the same secret entropy doesn't make sense"
        names			= {
            name: create(
                name		= name,
                group_threshold	= group_threshold,
                groups		= groups,
                master_secret	= master_secret,
                passphrase	= passphrase.encode( 'UTF-8' ) if passphrase else b'',
                using_bip39	= using_bip39,  # Derive wallet Seed using BIP-39 Mnemonic + passphrase generation
                cryptopaths	= cryptopaths,
            )
            for name in names or [ "SLIP39" ]
        }

    if text and using_bip39:
        # Output the BIP-39 Mnemonic phrase we're using to generate the Seed as text.  We'll label
        # it as BIP-39, but it will just be ignored by standard SLIP-39 recovery attempts.
        print( f"Using BIP-39 Mnemonic: {produce_bip39( entropy=master_secret )}" )

    cover_text			= None
    if cover_page:
        cover_text		= open(os.path.join(os.path.dirname(__file__), 'COVER.txt'), encoding='UTF-8').read()
        if using_bip39:
            cover_text	       += open(os.path.join(os.path.dirname(__file__), 'COVER-BIP-39.txt', ), encoding='UTF-8').read()
        else:
            cover_text	       += open(os.path.join(os.path.dirname(__file__), 'COVER-SLIP-39.txt'), encoding='UTF-8').read()

    # Generate each desired SLIP-39 Mnemonic cards PDF.  Supports --card (the default).  Remember
    # any deduced orientation and paper_format for below.
    results			= {}
    (pdf_paper,pdf_orient),pdf	= (None,None),None
    for name, details in names.items():
        # Get the first group of the accountgroups in details.accounts.
        accounts		= details.accounts
        assert accounts and accounts[0], \
            "At least one --cryptocurrency must be specified"
        for account in accounts[0]:
            log.warning( f"{account.crypto:6} {account.path:20}: {account.address}" )

        if text:
            # Output the SLIP-39 mnemonics as text, to stdout:
            #    name: <mnemonic>
            # or, if no name, just:
            #    <mnemonic>
            g_nam_max		= max( map( len, details.groups.keys() ))
            for g_name,(g_of,g_mnems) in details.groups.items():
                for i,mnem in enumerate( g_mnems ):
                    print( f"{name}: {g_name}: {i+1} of {len(g_mnems)}: {mnem}" )

        # Unless no card_format (False) or paper wallet password specified, produce a PDF containing
        # the SLIP-39 mnemonic recovery cards; remember the deduced (<pdf_paper>,<pdf_orient>).  If
        # we're producing paper wallets, always force portrait orientation for the cards, to match.
        if card_format is not False or wallet_pwd:
            (pdf_paper,pdf_orient),pdf,_ = produce_pdf(
                *details,
                card_format	= card_format or CARD,
                paper_format	= paper_format or PAPER,
                orientations	= ('portrait', ) if wallet_pwd else None,
                cover_text	= cover_text,
                watermark	= watermark,
            )

        now			= datetime.now()

        pdf_name		= ( filename or FILENAME_FORMAT ).format(
            name	= name,
            date	= datetime.strftime( now, '%Y-%m-%d' ),
            time	= datetime.strftime( now, '%H.%M.%S'),
            crypto	= accounts[0][0].crypto,
            path	= accounts[0][0].path,
            address	= accounts[0][0].address,
        )
        if not pdf_name.lower().endswith( '.pdf' ):
            pdf_name	       += '.pdf'

        if wallet_pwd:
            # Deduce the paper wallet size and create a template.  All layouts are in specified in
            # inches; template dimensions are in mm.
            try:
                (wall_h,wall_w),wall_margin = WALLET_SIZES[wallet_format.lower() if wallet_format else WALLET]
            except KeyError:
                (wall_h,wall_w),wall_margin = ast.literal_eval( wallet_format )

            wall		= layout_wallet( Coordinate( y=wall_h, x=wall_w ), wall_margin )  # converts to mm
            wall_dim		= wall.mm()

            # Lay out wallets, always in Portrait orientation, defaulting to the Card paper_format
            # if it is a standard size (a str, not an (x,y) tuple), otherwise to "Letter" paper.  Printers may
            # have problems with a PDF mixing Landscape and Portrait, but do it if desired...
            if wallet_paper is None:
                wallet_paper	= paper_format if type(paper_format) is str else PAPER

            pdf.add_page( orientation='P', format=wallet_paper )
            page_margin_mm	= PAGE_MARGIN * MM_IN

            walls_pp,page_xy	= layout_components( pdf, comp_dim=wall_dim, page_margin_mm=page_margin_mm )
            wall_elements	= list( wall.elements() )
            if log.isEnabledFor( logging.DEBUG ):
                log.debug( f"Wallet elements: {json.dumps( wall_elements, indent=4)}" )
            wall_tpl		= fpdf.FlexTemplate( pdf, wall_elements )

            # Place each Paper Wallet adding pages as necessary (we already have the first fresh page).
            wall_n		= 0
            page_n		= 0
            for account_group in accounts:
                for c_n,account in enumerate( account_group ):
                    p,(offsetx,offsety) = page_xy( wall_n )
                    if p != page_n:
                        pdf.add_page( orientation='P', format=wallet_paper )
                        page_n	= p
                    try:
                        private_enc		= account.encrypted( wallet_pwd )
                    except NotImplementedError as exc:
                        log.exception( f"{account.crypto} doesn't support BIP-38 or JSON wallet encryption: {exc}" )
                        continue

                    wall_n     += 1

                    images			= os.path.dirname( __file__ )
                    wall_tpl['wallet-bg']	= os.path.join( images, 'paper-wallet-background.png' )
                    wall_tpl[f"crypto-f{c_n}"]	= account.crypto
                    wall_tpl[f"crypto-b{c_n}"]	= account.crypto

                    wall_tpl['center']		= os.path.join( images, account.crypto + '.png' )

                    wall_tpl['name-label']	= "Wallet:"
                    wall_tpl['name-bg']		= os.path.join( images, '1x1-ffffff54.png' )
                    wall_tpl['name']		= name

                    # wall_tpl['center-bg']	= os.path.join( images, 'guilloche-center.png' )

                    public_qr	= qrcode.QRCode(
                        version		= None,
                        error_correction = qrcode.constants.ERROR_CORRECT_M,
                        box_size	= 10,
                        border		= 1,
                    )
                    public_qr.add_data( account.address )
                    wall_tpl['address-l-bg']	= os.path.join( images, '1x1-ffffff54.png' )
                    wall_tpl['address-l']	= account.address
                    wall_tpl['address-r-bg']	= os.path.join( images, '1x1-ffffff54.png' )
                    wall_tpl['address-r']	= account.address

                    wall_tpl['address-qr-t']	= 'PUBLIC ADDRESS'
                    wall_tpl['address-qr-bg']	= os.path.join( images, '1x1-ffffff54.png' )
                    wall_tpl['address-qr']	= public_qr.make_image( back_color="transparent" ).get_image()
                    wall_tpl['address-qr-b']	= 'DEPOSIT/VERIFY'
                    wall_tpl['address-qr-r']	= account.path

                    private_qr	= qrcode.QRCode(
                        version		= None,
                        error_correction = qrcode.constants.ERROR_CORRECT_M,
                        box_size	= 10,
                        border		= 1,
                    )
                    private_qr.add_data( private_enc )

                    wall_tpl['private-bg']	= os.path.join( images, '1x1-ffffff54.png' )

                    # If not enough lines, will throw Exception, as it should!  We don't want to
                    # emit a Paper Wallet without the entire encrypted private key present.  This is
                    # primarily an issue for Ethereum encrypted JSON wallets, which are very large.
                    # As the vertical aspect ratio of the Paper Wallet increases (eg. for half- or
                    # third-page vs. quarter-page Paper Wallets), the line length increases, but the
                    # number of lines available decreases.  Estimate the number of characters on
                    # each line.
                    line_elm			= next( e for e in wall_elements if e['name'] == 'private-0' )
                    line_points			= ( line_elm['x2'] - line_elm['x1'] ) / MM_IN * PT_IN
                    line_fontsize		= line_elm['size']
                    line_chars			= int( line_points / line_fontsize / ( 5 / 8 ))  # Chars ~ 5/8 width vs. height
                    log.debug( f"Private key line length: {line_chars} chars" )
                    for ln,line in enumerate( chunker( private_enc, line_chars )):
                        wall_tpl[f"private-{ln}"] = line
                    wall_tpl['private-hint-t']	= 'PASSWORD HINT:'
                    wall_tpl['private-hint-bg']	= os.path.join( images, '1x1-ffffff54.png' )
                    wall_tpl['private-hint']	= wallet_pwd_hint
                    wall_tpl['private-qr-t']	= 'PRIVATE KEY'
                    wall_tpl['private-qr-bg']	= os.path.join( images, '1x1-ffffff54.png' )
                    wall_tpl['private-qr']	= private_qr.make_image( back_color="transparent" ).get_image()
                    wall_tpl['private-qr-b']	= 'SPEND'

                    wall_tpl.render( offsetx=offsetx, offsety=offsety )

        if json_pwd:
            # If -j|--json supplied, also emit the encrypted JSON wallet.  This may be a *different*
            # password than the SLIP-39 master secret encryption passphrase.  It will be required to
            # decrypt and use the saved JSON wallet file, eg. to load a software Ethereum wallet.
            assert eth_account, \
                "The optional eth-account package is required to support output of encrypted JSON wallets\n" \
                "    python3 -m pip install eth-account"
            assert any( 'ETH' == crypto for crypto,paths in cryptopaths ), \
                "--json is only valid if '--crypto ETH' wallets are specified"

            for eth in (
                account
                for group in accounts
                for account in group
                if account.crypto == 'ETH'
            ):
                json_str	= json.dumps( eth_account.Account.encrypt( eth.key, json_pwd ), indent=4 )
                json_name	= ( filename or FILENAME_FORMAT ).format(
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
                    margin_mm	= PAGE_MARGIN * MM_IN
                    pdf.set_margin( 1.0 * MM_IN )

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
            if filepath is not None:  # ''/True path implies current dir.
                if filepath is True:
                    filepath	= ''
                pdf_path		= os.path.join( filepath, pdf_name ) if filepath else pdf_name
                log.warning( f"Writing SLIP39-encoded wallet for {name!r} to: {pdf_path}" )
                pdf.output( pdf_path )
            if printer is not None:  # if True, uses "default" printer
                printer		= None if printer is True else printer
                log.warning( f"Printing SLIP39-encoded wallet for {name!r} to: {printer or '(default)'}: " )
                printer_output(
                    pdf.output(),
                    printer		= printer,
                    orientation		= pdf_orient,
                    paper_format	= pdf_paper,
                )

        results[pdf_name]	= details

    return results
