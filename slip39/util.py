
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

import colorsys
import fractions
import getpass
import logging
import math
import sys

from functools		import wraps

# util.timer
#
# Select platform appropriate timer function
#
if sys.platform == 'win32' and sys.version_info[0:2] < (3,8):
    # On Windows (before Python 3.8), the best timer is time.clock
    from time		import clock	as timer
else:
    # On most other platforms the best timer is time.time
    from time		import time	as timer


#
# @util.timing
#
def timing( fun, instrument=False, level=None ):
    """A timing decorator which optionally instruments the function return value to return
    (duration,value), or logs the call duration (at logging.INFO by default, if not instrumenting).

    """
    @wraps( fun )
    def wrap( *args, **kwds ):
        beg			= timer()
        result			= fun( *args, **kwds )
        end			= timer()
        dur			= end - beg
        if level or not instrument:
            logging.log( level or logging.INFO, f"{fun!r} took {dur:.3f}s" )
        if instrument:
            return (dur,result)
        return result
    return wrap


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


def ordinal( num ):
    ordinal_dict		= {1: "st", 2: "nd", 3: "rd"}
    q, mod			= divmod( num, 10 )
    suffix			= q % 10 != 1 and ordinal_dict.get(mod) or "th"
    return f"{num}{suffix}"


def commas( seq, final_and=None ):
    """Replace any numeric sequences eg. 1, 2, 3, 5, 7 w/ 1-3, 5 and 7.  Caller should
    usually sort numeric values before calling."""
    def int_seq( seq ):
        for i,iv in enumerate( seq[:-1] ):
            if type(iv) in (int,float):
                for j,jv in enumerate( seq[i:] ):
                    if type(jv) not in (int,float) or jv != iv + j:
                        j      -= 1
                        break
                if j > 1:
                    return (i,i+j)
        return None
    seq				= list( seq )
    while rng := int_seq( seq ):
        #print( f"int_seq: series {rng!r} ({seq[rng[0]]!r} - {seq[rng[1]]!r}) found in {seq!r}"  )
        beg			= seq[:rng[0]]
        nxt			= rng[1] + 1
        end			= seq[nxt:] if nxt < len( seq ) else []
        seq			= beg + [f"{seq[rng[0]]}-{seq[rng[1]]}"] + end
    if final_and and len(seq) > 1:
        seq			= seq[:-2] + [f"{seq[-2]} and {seq[-1]}"]
    return ', '.join( map( str, seq ))


def round_onto( value, keys, keep_sign=True ):
    """Find the numeric key closest to value, maintaining sign if possible.  None and other
    non-numeric values are supported if they are present in keys.

    """
    if value in keys:
        return value
    keys			= sorted( k for k in keys if type(k) in (float,int) )
    near, near_i		= min(
        (abs( k - value), i)
        for i, k in enumerate( keys )
    )
    if keep_sign and (( value < 0 ) != ( keys[near_i] < 0 )):
        # The sign differs; if value -'ve but closest was +'ve, and there is a lower key available
        if value < 0:
            if near_i > 0:
                near_i	       -= 1
        else:
            if near_i + 1 < len( keys ):
                near_i	       += 1
    return keys[near_i]


entropy_signal_strengths	= {
    3: "very bad",
    2: "bad",
    1: "poor",
    0: "weak",
    -1: "ok",
    -2: "strong",
    None: "excellent",
}


def entropy_rating_dB( dB ):
    return entropy_signal_strengths[round_onto( dB, entropy_signal_strengths.keys(), keep_sign=True )]


def rate_dB( dB, what=None ):
    rating			= entropy_rating_dB( dB )
    result			= ''
    if what:
        result		       += f"{what}: "
    result		       += f"{dB:.1f}dB" if type( dB ) in (int,float) else f"{dB}"
    result		       += f" ({rating})"
    return result


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


def exponential_moving_average( current, sample, weight ):
    """exponential_moving_average -- rolling average without any data history

    Computes an exponential moving average:

        ( 1 - weight ) * current + weight * sample

    where the incoming sample has the given weight, and current samples have exponentially less
    influence on the current value.  Ignores a current value of None.

    """
    return sample if current is None else current + weight * ( sample - current )


def avg( seq ):
    vals			= list( seq )
    if vals:
        return sum( vals ) / len( vals )
    return math.nan


def rms( seq ):
    """Computes RMS for real/complex sequence of values"""
    if seq:
        return math.sqrt( avg( abs( s ) ** 2 for s in seq ))
    return 0


def is_power_of_2( n: int ) -> bool:
    return not ( n & ( n - 1 ))


class mixed_fraction( fractions.Fraction ):
    """A Fraction that represents whole multiples of itself as eg. 1-1/2"""
    def __str__( self ):
        whole, rest		= divmod( self.numerator, self.denominator )
        if whole and rest:
            return f"{whole}+{fractions.Fraction( rest, self.denominator)}"
        return super().__str__()
