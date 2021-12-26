from collections	import namedtuple


from .defaults		import FONTS


class Region:
    """Takes authority for a portion of another Region, and places things in it, relative to its
    upper-left and lower-right corners."""
    def __init__( self, name, x1=None, y1=None, x2=None, y2=None, rotate=None ):
        self.name		= name
        self.x1			= x1		# could represent positions, offsets or ratios
        self.y1			= y1
        self.x2			= x2
        self.y2			= y2
        self.rotate		= rotate
        self.regions		= []

    def element( self ):
        "Converts to mm."
        return dict(
            name	= self.name,
            x1		= self.x1 * 25.4,
            y1		= self.y1 * 25.4,
            x2		= self.x2 * 25.4,
            y2		= self.y2 * 25.4,
            rotate	= self.rotate or 0.0
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
        region.x1		= self.x1 + ( self.x2 - self.x1 ) * ( 0 if region.x1 is None else region.x1 )
        region.y1		= self.y1 + ( self.y2 - self.y1 ) * ( 0 if region.y1 is None else region.y1 )
        region.x2		= self.x1 + ( self.x2 - self.x1 ) * ( 1 if region.x2 is None else region.x2 )
        region.y2		= self.y1 + ( self.y2 - self.y1 ) * ( 1 if region.y2 is None else region.y2 )
        self.regions.append( region )
        return region

    def dimensions( self ):
        "Converts to mm."
        return Coordinate( (self.x2 - self.x1) * 25.4, (self.y2 - self.y1) * 25.4 )

    def elements( self ):
        """Yield a sequence of { 'name': "...", 'x1': #,  ... }"""
        if self.__class__ != Region:
            yield self.element()
        for r in self.regions:
            for d in r.elements():
                yield d


class Text( Region ):
    def __init__( self, *args, font=None, text=None, size=None, size_ratio=None, align=None,
                  foreground=None, background=None, bold=None, italic=None, underline=None,
                  **kwds ):
        self.font		= font
        self.text		= text
        self.size		= size
        self.size_ratio		= size_ratio or 2/3
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
        line_height		= (self.y2 - self.y1) * 72      # points
        d['size']		= self.size or int( round( line_height * self.size_ratio ))
        if self.text is not None:
            d['text']		= self.text
        if self.bold:
            d['bold']		= True
        if self.italic:
            d['italic']		= True
        if self.underline:
            d['underline']		= True
        if self.align is not None:
            d['align']		= self.align
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


def card(
    card_size: Coordinate,
    card_margin: int,
):
    card			= Box( 'card', 0, 0, card_size.x, card_size.y )
    card_interior		= card.add_region_relative(
        Region( 'card-interior', x1=+card_margin, y1=+card_margin, x2=-card_margin, y2=-card_margin )
    )
    card_interior.add_region_proportional(
        Text( 'card-group', x1=1/8, y1=-1/8, x2=7/8, y2=3/8, foreground=0xFFCCCC, rotate=-45 )  # almost white
    )
    card_top			= card_interior.add_region_proportional(
        Region( 'card-top', x1=0, y1=0, x2=1, y2=1/4 )
    )
    card_bottom			= card_interior.add_region_proportional(
        Region( 'card-bottom', x1=0, y1=1/4, x2=1, y2=1 )
    )
    card_mnemonics		= card_bottom.add_region_proportional(
        Region( 'card-mnemonics', x1=0, y1=0, x2=3/4, y2=1 )
    )
    card_qr			= card_bottom.add_region_proportional(
        Image( 'card-qr', x1=3/4, y1=0, x2=1, y2=1 )
    )
    card_qr.y2			= card_qr.y1 + (card_qr.x2 - card_qr.x1)  # make height same as width

    card_top.add_region_proportional(
        Text( 'card-title', x1=0, y1=0, x2=1, y2=44/100, bold=True )
    )
    card_top.add_region_proportional(
        Text( 'card-requires', x1=0, y1=45/100, x2=1, y2=75/100, align='C', italic=True )
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
    return card
