import colorsys
import getpass
import logging
import sys


log_cfg				= {
    "level":	logging.WARNING,
    "datefmt":	'%Y-%m-%d %H:%M:%S',
    #"format":	'%(asctime)s.%(msecs).03d %(threadName)10.10s %(name)-16.16s %(levelname)-8.8s %(funcName)-10.10s %(message)s',
    "format":	'%(asctime)s %(name)-16.16s %(message)s',
}

log_levelmap 			= {
    -2: logging.FATAL,
    -1: logging.ERROR,
    0: logging.WARNING,
    1: logging.INFO,
    2: logging.DEBUG,
}


def log_level( adjust ):
    """Return a logging level corresponding to the +'ve/-'ve adjustment"""
    return log_levelmap[
        max(
            min(
                adjust,
                max( log_levelmap.keys() )
            ),
            min( log_levelmap.keys() )
        )
    ]


def ordinal(num):
    ordinal_dict		= {1: "st", 2: "nd", 3: "rd"}
    q, mod			= divmod( num, 10 )
    suffix			= q % 10 != 1 and ordinal_dict.get(mod) or "th"
    return f"{num}{suffix}"


def input_secure( prompt, secret=True, file=None ):
    """When getting secure (optionally secret) input from standard input, we don't want to use getpass, which
    attempts to read from /dev/tty.

    """
    if ( file or sys.stdin ).isatty():
        # From TTY; provide prompts, and do not echo secret input
        if secret:
            return getpass.getpass( prompt, stream=file )
        elif file:
            # Coming from some file; no prompt, read a line from the file source
            return file.readline()
        else:
            return input( prompt )
    else:
        # Not a TTY; don't litter pipeline output with prompts
        if file:
            return file.readline()
        return input()


def chunker( sequence, size ):
    while sequence:
        yield sequence[:size]
        sequence		= sequence[size:]


def hex_to_rgb( value, real=False, precision=4 ):
    """
    Convert hex color to ints, or reals rounded to a certain precision.

    >>> hex_to_rgb( "#ffffff" )
    (255, 255, 255)
    >>> hex_to_rgb( "#ffffffffffff" )
    (65535, 65535, 65535)
    >>> hex_to_rgb( "#ffffffffffff", real=True )
    (1.0, 1.0, 1.0)
    >>> hex_to_rgb( "#ffff80002000", real=True )
    (1.0, 0.5, 0.125)
    """
    nibble			= value.lstrip('#')
    nibs			= len( nibble )
    ints			= ( int( nibble[i:i + nibs // 3], 16 ) for i in range( 0, nibs, nibs // 3 ))
    return tuple( ( round( i / ( 16 ** ( nibs // 3 ) - 1 ), precision ) for i in ints ) if real else ints )


def rgb_to_hex( *rgb, bits=None, nibs=None ):
    """Convert int/real RGB values to hex.  For ints, assumes 8-bit values in range [0-255); for
    [0,65535), use bits=16.  For real-valued rgb in range (0,1), use bits=1.

    By default, will try to auto-select between bits=0/8/16, by examining rgb values; if all are <1,
    or <=1 and are float, then bits=0; otherwise if any are > 255, then bits=16.

    >>> rgb_to_hex( 255, 255, 255 )
    '#ffffff'
    >>> rgb_to_hex( 65535, 65535, 65535 )
    '#ffffffffffff'

    >>> rgb_to_hex( .5, .5, .5 )		# deduces (0,1)
    '#808080'

    >>> rgb_to_hex( .5, .75, .9, nibs=3  )	# same, but force 3 nibbles
    '#800bffe66'

    >>> rgb_to_hex( 11, 111, 1111 )		# deduces (0,65535]
    '#000b006f0457'

    >>> rgb_to_hex( 288, 255, 254, bits=8 )	# force 8-bit colors, w/ truncation
    '#fffffe'
    """
    assert len( rgb ) == 3, \
        "Requires RGB values"
    if bits is None:
        if all( c < 1 for c in rgb ) or all( c <= 1 and type( c ) is float for c in rgb ):
            bits		= 1
        elif any( c > 255 for c in rgb ):
            bits		= 16
        else:
            bits		= 8

    if nibs is None:
        nibs			= 2 if bits == 1 else bits // 4 + ( 1 if ( bits % 4 ) else 0 )

    end				= 2 ** bits - 1
    reals			= tuple( c / end for c in rgb )
    one				= 16 ** nibs - 1
    ints			= ( max( 0, min( one, int( round( r * one )))) for r in reals )

    return '#' + ''.join( "{i:0{nibs}x}".format( nibs=nibs, i=i ) for i in ints )


def hue_shift( color, shift=1/3 ):
    """Take a hex or (r,g,b) value, and shift its Hue "right" in the HSV spectrum by the given shift
    percentage (default: .1, or 10%).  Requires either '#aabbcc' hex colors, or real-values RGB in
    the range (0,1).

    >>> hue_shift( '#ff0000', shift=0 )
    '#ff0000'

    >>> hue_shift( '#ff0000', shift=1/3 )
    '#00ff00'

    >>> hue_shift( '#ff0000', shift=-1/3 )
    '#0000ff'

    >>> hue_shift( '#ff0000', shift=2/3 )
    '#0000ff'

    >>> hue_shift( '#ff0000', shift=1/2 )
    '#00ffff'

    >>> hue_shift( '#ff0000', shift=1/4 )
    '#80ff00'

    >>> hue_shift( '#ff0000', shift=1/10 )
    '#ff9900'

    >>> hue_shift( '#800000', shift=1/10 )
    '#804d00'

    >>> hue_shift( '#48c', shift=1/3 )
    '#cc4488'

    >>> hue_shift( (4/15, 8/15, 12/15), shift=-2/3 )  # Same RGB, but Hue shifted the other way 'round
    '#cc4488'
    """
    if isinstance( color, str ):
        rgb			= hex_to_rgb( color, real=1 )
    else:
        rgb			= tuple( color )
    assert len( rgb ) == 3 and all( 0.0 <= c <= 1.0 for c in rgb ), \
        f"Invalid RGB values for hue shift: {rgb!r}"
    h,s,v			= colorsys.rgb_to_hsv( *rgb )
    #log.warning( f"Color {color!r} == RGB {rgb!r} == HSV{(h,s,v)!r}" )
    h				= ( h + shift ) % 1.0  # if shift is -'ve, % (modulo) correctly shifts to +'ve
    rgb				= colorsys.hsv_to_rgb( h, s, v )
    return rgb_to_hex( *rgb )
