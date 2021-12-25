from collections	import namedtuple

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
