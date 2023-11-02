# -*- mode: python ; coding: utf-8 -*-
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

import logging
import math

from collections	import namedtuple
from typing		import Tuple, Callable, Type, Optional

from fpdf		import FPDF

from ..util		import ordinal
from ..defaults		import (
    FONTS, MNEM_ROWS_COLS, MM_IN, PT_IN, COLOR, PAGE_MARGIN,
)

log				= logging.getLogger( __package__ )


class Region:
    """Takes authority for a portion of another Region, and places things in it, relative to its
    upper-left and lower-right corners.

    Attempts to create a sane priority hierarchy, because fpdf2's FlexTemplate sorts based on it.
    If a specific priority is provided, it will be used.  However, if no priority is given, 0 will
    be automatically assigned by FlexTemplate.  If sorting is unstable, this may result in an
    unspecified ordering.

    """
    def __init__( self, name, x1=None, y1=None, x2=None, y2=None, rotate=None, priority=None ):
        self.name		= name
        self.x1			= x1		# could represent positions, offsets or ratios
        self.y1			= y1
        self.x2			= x2
        self.y2			= y2
        self.rotate		= rotate
        self.priority		= priority
        self.regions		= []

    @property
    def h( self ):
        return self.y2 - self.y1

    @property
    def w( self ):
        return self.x2 - self.x1

    def element( self ):
        "Converts to mm.  Optionally returns a specified priority."
        d			= dict(
            name	= self.name,
            x1		= self.x1 * MM_IN,
            y1		= self.y1 * MM_IN,
            x2		= self.x2 * MM_IN,
            y2		= self.y2 * MM_IN,
            rotate	= self.rotate or 0.0
        )
        if self.priority:
            d['priority']	= self.priority
        return d

    def __str__( self ):
        return f"({self.name:16}: ({float(self.x1):8}, {float( self.y1):8}) - ({float(self.x2):8} - {float(self.y2):8})"

    def add_region( self, region ):
        region.x1		= self.x1 if region.x1 is None else region.x1
        region.y1		= self.y1 if region.y1 is None else region.y1
        region.x2		= self.x2 if region.x2 is None else region.x2
        region.y2		= self.y2 if region.y2 is None else region.y2
        self.regions.append( region )
        return region

    def add_region_relative( self, region ):
        region.x1		= self.x1 + ( region.x1 or 0 )
        region.y1		= self.y1 + ( region.y1 or 0 )
        region.x2		= self.x2 + ( region.x2 or 0 )
        region.y2		= self.y2 + ( region.y2 or 0 )
        self.regions.append( region )
        return region

    def add_region_proportional( self, region ):
        region.x1		= self.x1 + self.w * ( 0 if region.x1 is None else region.x1 )
        region.y1		= self.y1 + self.h * ( 0 if region.y1 is None else region.y1 )
        region.x2		= self.x1 + self.w * ( 1 if region.x2 is None else region.x2 )
        region.y2		= self.y1 + self.h * ( 1 if region.y2 is None else region.y2 )
        self.regions.append( region )
        return region

    def square( self, maximum=None, justify=None ):
        """Make a region square (of 'maximum' size), justifying it L/C/R, and/or T/M/B; default is Center/Middle"""
        dims			= min( self.w, self.h )
        if maximum:
            dims		= min( dims, maximum )
        justify			= ( justify or '' ).upper()
        if 'L' in justify:
            self.x2		= self.x1 + dims
        elif 'R' in justify:
            self.x1		= self.x2 - dims
        else:  # 'C' is default
            self.x1, self.x2	= self.x1 + ( self.w - dims ) / 2, self.x2 - ( self.w - dims ) / 2
        if 'T' in justify:
            self.y2		= self.y1 + dims
        elif 'B' in justify:
            self.y1		= self.y2 - dims
        else:  # 'M' is default
            self.y1, self.y2	= self.y1 + ( self.h - dims ) / 2, self.y2 - ( self.h - dims ) / 2
        return self

    def mm( self ):
        "Dimensions as Coordinate( x, y ) in mm."
        return Coordinate( self.w * MM_IN, self.h * MM_IN )

    dimensions 			= mm

    def elements( self ):
        """Yield a sequence of { 'name': "...", 'x1': #,  ... }."""
        if self.__class__ != Region:
            yield self.element()
        for r in self.regions:
            for d in r.elements():
                yield d


class Text( Region ):
    SIZE_RATIO			= 3/4

    def __init__( self, *args, font=None, style=None, text=None, size=None, size_ratio=None, align=None, multiline=None,
                  foreground=None, background=None, bold=None, italic=None, underline=None,
                  **kwds ):
        self.font		= font		# "dejavu"
        self.style		= style		# eg. "BI".  Or, built (in fpdf) from self.bold, self.italic
        self.text		= text
        self.multiline		= multiline
        self.size		= size
        self.size_ratio		= size_ratio or self.SIZE_RATIO
        self.align		= align
        self.foreground		= foreground
        self.background		= background
        self.bold		= bold
        self.italic		= italic
        self.underline		= underline
        super().__init__( *args, **kwds )

    def element( self ):
        d			= super().element()
        d['type']		= 'T'
        d['font']		= FONTS.get( self.font ) or self.font or FONTS.get( 'sans' )
        if self.style:
            d['style']		= self.style
        line_height		= self.h * PT_IN  # Postscript point == 1/72 inch
        d['size']		= self.size or ( line_height * self.size_ratio )  # No need for int(round(..))
        if self.text is not None:
            d['text']		= self.text
        if self.bold:
            d['bold']		= True
        if self.italic:
            d['italic']		= True
        if self.underline:
            d['underline']	= True
        if self.align is not None:
            d['align']		= self.align
        if self.multiline is not None:
            d['multiline']	= bool( self.multiline )
        if self.foreground is not None:
            d['foreground']	= self.foreground
        if self.background is not None:
            d['background']	= self.background
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


def layout_card(
    card_size: Coordinate,
    card_margin: int,
    num_mnemonics: int	= 20,
):
    card			= Box( 'card', 0, 0, card_size.x, card_size.y )
    card_interior		= card.add_region_relative(
        Region( 'card-interior', x1=+card_margin, y1=+card_margin, x2=-card_margin, y2=-card_margin )
    )

    # Rotate the card group, watermark, etc. so its angle is from the lower-left to the upper-right.
    #
    #             b
    #      +--------------+
    #      |           .
    #    a |       .
    #      | β .    c
    #      + 90-β
    #
    #   tan(β) = b / a, so
    #   β = arctan(b / a)
    #
    a				= card_interior.h
    b				= card_interior.w
    c				= math.sqrt( a * a + b * b )
    β				= math.atan( b / a )
    rotate			= 90 - math.degrees( β )

    for c_n in range( 16 ):  # SLIP-39 supports up to 16 groups
        card_interior.add_region_proportional( Text(
            f'card-g{c_n}', x1=c/b * 8/100, y1=-2/32, x2=c/b * 92/100, y2=10/32,
            foreground	= int( COLOR[c_n % len( COLOR )], 16 ),
            rotate	= -rotate,
            bold	= True,
        ))
    card_interior.add_region_proportional( Text(
        'card-watermark', x1=5/100, y1=14/16, x2=c/b * 95/100, y2=17/16,
        foreground	= int( COLOR[-2], 16 ),
        rotate		= rotate,  # eg 60
        align		= 'L'
    ))

    # Rotation is downward around upper-left corner; so, lower-left corner will shift 1 height
    # leftward and upward; so start 1 height right and down.
    link_length			= card_interior.h
    link_height			= link_length * 6/32
    card_interior.add_region(
        Text(
            'card-link',
            x1		= card_interior.x1 + link_height,
            y1		= card_interior.y1,
            x2		= card_interior.x1 + link_height + link_length,
            y2		= card_interior.y1 + link_height,
            rotate	= -90,				# along left border of card
            foreground	= int( COLOR[-3], 16 ), 	# Light grey
            align	= 'R'
        )
    )

    card_top			= card_interior.add_region_proportional(
        Region( 'card-top', x1=0, y1=0, x2=1, y2=1/4 )
    )
    card_bottom			= card_interior.add_region_proportional(
        Region( 'card-bottom', x1=0, y1=1/4, x2=1, y2=1 )
    )
    card_mnemonics		= card_bottom.add_region_proportional(
        Region( 'card-mnemonics', x1=0, y1=0, x2=13/16, y2=1 )
    )
    # QR code for Card Mnemonics on back is center/middle of Mnemonics area
    card_mnemonics.add_region(
        Image( 'card-qr-mnem' )
    ).square( justify='T' )

    # QR codes sqaare, and anchored to top and bottom of card.
    card_bottom.add_region_proportional(
        Image( 'card-qr1', x1=13/16, y1=0, x2=1, y2=1/2 )
    ).square( justify='TR' )
    card_bottom.add_region_proportional(
        Image( 'card-qr2', x1=13/16, y1=1/2, x2=1, y2=1 )
    ).square( justify='BR' )

    card_top.add_region_proportional(
        Text( 'card-title', x1=0, y1=0, x2=1, y2=40/100, bold=True )
    )
    card_top.add_region_proportional(
        Text( 'card-requires', x1=0, y1=40/100, x2=1, y2=66/100, align='C', italic=True )
    )
    card_top.add_region_proportional(
        Text( 'card-crypto1', x1=0, y1=66/100, x2=1, y2=83/100, align='R' )
    )
    card_top.add_region_proportional(
        Text( 'card-crypto2', x1=0, y1=83/100, x2=1, y2=100/100, align='R' )
    )

    assert num_mnemonics in MNEM_ROWS_COLS, \
        f"Invalid SLIP-39 mnemonic word count: {num_mnemonics}"
    rows,cols			= MNEM_ROWS_COLS[num_mnemonics]
    for r in range( rows ):
        for c in range( cols ):
            card_mnemonics.add_region_proportional(
                Text(
                    f"mnem-{c * rows + r}",
                    x1		= c/cols,
                    y1		= r/rows,
                    x2		= (c+1)/cols,
                    y2		= (r+1)/rows,
                    font	= 'mono',
                    bold	= True,
                    size_ratio	= 9/16,
                )
            )

    return card


def layout_wallet(
    wallet_size: Coordinate,
    wallet_margin: int,
):
    """Produce a template format for a Paper Wallet.

    Sets priority:
      -3     : Hindmost backgrounds
      -2     : Things atop background, but beneath contrast-enhancement
      -1     : Contrast-enhancing partially transparent images
       0     : Text, etc. (the default)
    """
    prio_backing		= -3
    prio_normal			= -2
    prio_contrast		= -1

    wallet			= Box( 'wallet', 0, 0, wallet_size.x, wallet_size.y )
    wallet_background		= wallet.add_region_proportional(  # noqa: F841
        Image( 'wallet-bg', priority=prio_backing ),
    )

    # Most of the Paper Wallet is visible (contains public address information).  The right-most
    # portion can be folded over, and displays private key information
    show			= wallet.add_region_proportional(
        Region( 'wallet-show', x2=5/8 )
    )
    fold			= wallet.add_region_proportional(
        Box( 'wallet-fold', x1=5/8 )
    )

    public			= show.add_region_relative(
        Region( 'wallet-public', x1=+wallet_margin, y1=+wallet_margin, x2=-wallet_margin, y2=-wallet_margin )
    )
    private			= fold.add_region_relative(
        Region( 'wallet-private', x1=+wallet_margin, y1=+wallet_margin, x2=-wallet_margin, y2=-wallet_margin )
    )

    # Assign each different Crypto name a different color, in template labels crypto-{f,b}1, crypto-{f,b}2, ...
    for c_n in range( len( COLOR )):
        public.add_region_proportional(
            Text( f'crypto-f{c_n}', x1=1/8, y1=-1/16, x2=7/8, y2=7/16, foreground=int( COLOR[c_n], 16 ), rotate=-45, priority=prio_normal )
        )
        private.add_region_proportional(
            Text( f'crypto-b{c_n}', x1=2/8, y1=-1/16, x2=7/8, y2=7/16, foreground=int( COLOR[c_n], 16 ), rotate=-45, priority=prio_normal )
        )

    # The background rosette and cryptocurrency symbol in the center
    public_center_size		= min( public.w, public.h )
    public.add_region(
        Image(
            'center',
            x1		= public.x1 + public.w * 2/3 - public_center_size / 3,
            y1		= public.y1 + public.h * 1/2 - public_center_size / 3,
            x2		= public.x1 + public.w * 2/3 + public_center_size / 3,
            y2		= public.y1 + public.h * 1/2 + public_center_size / 3,
        )
    )

    # Public addresses are vertical on left- and right-hand of public Region.  In order to fit the
    # longer ETH addresses into a space with a fixed-width font, we know that the ratio of the width
    # to the height has to be about 1/20.  Rotation is downward around upper-left corner; so,
    # lower-left corner will shift 1 height leftward and upward; so start 1 height right and down.
    address_length		= public.h
    address_height		= address_length * 1/20
    public.add_region(
        Image(
            'address-l-bg',
            x1		= public.x1 + address_height,
            y1		= public.y1,
            x2		= public.x1 + address_height + address_length,
            y2		= public.y1 + address_height,
            rotate	= -90,
            priority	= prio_contrast,
        )
    ).add_region(
        Text(
            'address-l',
            font	= 'mono',
            rotate	= -90,
        )
    )

    # Rotation is upward around the upper-left corner, so lower-left corner will shift 1 height
    # upward and right; so start 1 height leftward and down.
    public.add_region(
        Image(
            'address-r-bg',
            x1		= public.x2 - address_height,
            y1		= public.y2,
            x2		= public.x2 - address_height + address_length,
            y2		= public.y2 + address_height,
            rotate	= +90,
            priority	= prio_contrast,
        )
    ).add_region(
        Text(
            'address-r',
            font	= 'mono',
            rotate	= +90,
        )
    )

    # Wallet name, amount
    public.add_region_proportional(
        Text( 'name-label',	x1=1/16, y1=0/16, x2=4/16, y2=1/16 )
    )
    public.add_region_proportional(
        Image( 'name-bg',	x1=4/16, y1=0/16, x2=15/16, y2=1/16, priority=prio_contrast )
    )
    public.add_region_proportional(
        Text( 'name',		x1=4/16, y1=0/16, x2=15/16, y2=1/16 )
    )

    public.add_region_proportional(
        Text( 'amount-label',	x1=1/16, y1=3/16, x2=4/16, y2=1/16 )
    )
    public.add_region_proportional(
        Image( 'amount-bg',	x1=4/16, y1=0/16, x2=15/16, y2=1/16, priority=prio_contrast )
    )
    public.add_region_proportional(
        Text( 'amount',		x1=4/16, y1=0/16, x2=15/16, y2=1/16 )
    )

    # Make Public QR Code square w/ min of height, width, anchored at lower-left corner
    public.add_region_proportional(
        Text( 'address-qr-t',	x1=1/16, y1=5/16, x2=1, y2=6/16 )
    )
    public_qr			= public.add_region_proportional(
        Image( 'address-qr-bg',	x1=1/16, y1=6/16, x2=1, y2=15/16 )
    ).square( justify='BL' )
    public_qr.add_region(
        Image( 'address-qr' )
    )

    public.add_region_proportional(
        Text( 'address-qr-b',	x1=1/16, y1=15/16, x2=1, y2=16/16 )
    )
    public_qr_r			= public.add_region_proportional(
        Text( 'address-qr-r',	x1=1/16, y1=6/16, x2=1, y2=7/16, rotate=-90 )
    )
    public_qr_r.x1	       += public_qr.w + public_qr_r.h
    public_qr_r.x2	       += public_qr.w

    # Private region

    private.add_region_proportional(
        Text( 'private-qr-t',	x1=0/16, y1=5/16, x2=1, y2=6/16 )
    )
    # QR code at most 5/8 the width, to retain sufficient space for large Ethereum encrypted JSON
    # wallet private keys
    private_qr			= private.add_region_proportional(
        Image( 'private-qr-bg',	x1=0/16, y1=6/16, x2=1, y2=15/16, priority=prio_contrast )
    ).square( maximum=private.w * 5 / 8, justify='BL' )
    private_qr.add_region(
        Image( 'private-qr' )
    )
    private.add_region_proportional(
        Text( 'private-qr-b',	x1=0/16, y1=15/16, x2=1, y2=16/16 )
    )

    # Hint above; but same computed width as private_qr
    private_h_t			= private.add_region_proportional(
        Text( 'private-hint-t',	x1=0/16, y1=0/16, x2=1, y2=1/16 )
    )
    private_h_t.x2		= private_qr.x2
    private_h_bg		= private.add_region_proportional(
        Image( 'private-hint-bg',x1=0/16, y1=1/16, x2=1, y2=4/16, priority=prio_contrast )
    )
    private_h_bg.x2		= private_qr.x2
    private_h			= private.add_region_proportional(
        Text( 'private-hint',	x1=0/16, y1=1/16, x2=1, y2=3/16 )
    )
    private_h.x2		= private_qr.x2

    # We'll use the right side of the private region, each line rotated 90 degrees down and right.
    # So, we need the upper-left corner of the private-bg anchored at the upper-right corner of
    # private.
    private_length		= private.h                     # line length is y-height
    private_fontsize		= 6.5				# points == 1/72 inch
    private_height		= private.x2 - private_qr.x2 - .05
    private_lineheight		= private_fontsize / PT_IN / Text.SIZE_RATIO * .9  # in.

    private.add_region(
        Image(
            'private-bg',
            x1		= private.x2,
            y1		= private.y1,
            x2		= private.x2 + private_length,
            y2		= private.y1 + private_height,
            rotate	= -90,
            priority	= prio_contrast,
        )
    )
    # Now, add private key lines down the edge from right to left, rotating each into place
    for ln in range( int( private_height // private_lineheight )):
        private.add_region(
            Text(
                f"private-{ln}",
                font	= 'mono',
                x1	= private.x2 - private_lineheight * ln,
                y1	= private.y1,
                x2	= private.x2 + private_length,
                y2	= private.y1 + private_lineheight,
                size	= private_fontsize,
                rotate	= -90,
            )
        )

    return wallet


def page_dimensions(
    pdf: FPDF,
    page_margin_mm: Optional[float] = None,   # eg. 1/4" in mm.
) -> Type[Coordinate]:
    """Compute the working page dimensions.  FPDF().epw/.eph incl. orienation, excl. margins.

    """
    if page_margin_mm is None:
        page_margin_mm		= PAGE_MARGIN * MM_IN
    return Coordinate(
        x	= pdf.epw - page_margin_mm * 2,
        y	= pdf.eph - page_margin_mm * 2
    )


def layout_components(
    pdf: FPDF,
    comp_dim: Coordinate,
    page_margin_mm: Optional[float] = None,     # eg. 1/4" in mm.
    bleed: Optional[float]	= None,	        # eg. 5%
) -> Tuple[int, Callable[[int],Tuple[int, Type[Coordinate]]]]:
    """Compute the number of components per pdf page, and a function returning the page # and component
    (x,y) for the num'th component.

    """
    if page_margin_mm is None:
        page_margin_mm		= PAGE_MARGIN * MM_IN
    # Allow 5% bleed over into page margins (to allow for slight error in paper vs. comp sizes)
    if bleed is None:
        bleed			= 5/100
    # FPDF().epw/.eph is *without* page margins, but *with* re-orienting for portrait/landscape
    comp_cols			= int(( pdf.epw - page_margin_mm * 2 * min( 1, 1 - bleed )) // comp_dim.x )
    comp_rows			= int(( pdf.eph - page_margin_mm * 2 * min( 1, 1 - bleed )) // comp_dim.y )
    comps_pp			= comp_rows * comp_cols

    # Compute actual page margins to center cards.
    page_margin_tb		= ( pdf.eph - comp_rows * comp_dim.y ) / 2
    page_margin_lr		= ( pdf.epw - comp_cols * comp_dim.x ) / 2

    def page_xy( num: int ) -> Tuple[int, Coordinate]:
        """Returns the page, and the coordinates within that page of the num'th component"""
        page,nth		= divmod( num, comps_pp )
        page_rows,page_cols	= divmod( nth, comp_cols )
        offsetx			= page_margin_lr + page_cols * comp_dim.x
        offsety			= page_margin_tb + page_rows * comp_dim.y
        log.debug( f"{ordinal(num)} {comp_dim.x:7.5f}mm x {comp_dim.y:7.5f}mm component on page {page}, offset {offsetx:7.5f}mm x {offsety:7.5f}mm" )
        return (page, Coordinate( x=offsetx, y=offsety ))

    return (comps_pp, page_xy)
