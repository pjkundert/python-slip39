
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

import colorsys
import getpass
import logging
import math
import sys
import traceback

from typing		import Union
from fractions		import Fraction
from functools		import wraps


__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( "util" )

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


def log_apis( func ):
    """Decorator for logging function args, kwds, and results"""
    @wraps( func )
    def wrapper( *args, **kwds ):
        try:
            result = func(*args, **kwds)
        except Exception as exc:
            log.warning( f"{func.__name__}( {args!r} {kwds!r} ): {exc}" )
        else:
            log.info( f"{func.__name__}( {args!r} {kwds!r} ) == {result}" )
        return result
    return wrapper


#
# util.is_...		-- Test for various object capabilities
#
def is_mapping( thing ):
    """See if the thing implements the Mapping protocol."""
    return hasattr( thing, 'keys' ) and hasattr( thing, '__getitem__' )


def is_listlike( thing ):
    """Something like a list or tuple; indexable, but not a string or a class (some may have
    __getitem__, eg. cpppo.state, based on a dict).

    """
    return not isinstance( thing, (str,bytes,type) ) and hasattr( thing, '__getitem__' )


#
# @util.memoize		-- Cache function results data based on positional args, and maxage/size
#
def memoize( maxsize=None, maxage=None, log_at=None ):
    """A very simple memoization wrapper based on (immutable) args only, for simplicity.  Any
    keyword arguments must be immaterial to the successful outcome, eg. timeout, selection of
    providers, etc..

    Only successful (non-Exception) outcomes are cached!

    Keeps track of the age (in seconds) and usage (count) of each entry, updating them on each call.
    When an entry exceeds maxage, it is purged.  If the memo dict exceeds maxsize entries, 10% are
    purged.

    Optionally logs when we memoize something, at level log_at.
    """
    def decorator( func ):
        @wraps( func )
        def wrapper( *args, **kwds ):
            now			= timer()
            # A 0 hits count is our sentinel indicating args not memo-ized
            last,hits		= wrapper._stat.get( args, (now,0) )
            if not hits or ( maxage and ( now - last > maxage )):
                entry = wrapper._memo[args] = func( *args, **kwds )
                if log_at and log.isEnabledFor( log_at ):
                    if hits:
                        log.log( log_at, "{} Refreshed {!r} == {!r}".format( wrapper.__name__, args, entry ))
                    else:
                        log.log( log_at, "{} Memoizing {!r} == {!r}".format( wrapper.__name__, args, entry ))
            else:
                entry		= wrapper._memo[args]
                #log.detail( "{} Remembers {!r} == {!r}".format( wrapper.__name__, args, entry ))
            hits	       += 1
            wrapper._stat[args] = (now,hits)

            if maxsize and len( wrapper._memo ) > maxsize:
                # Prune size, by ranking each entry by hits/age.  Something w/:
                #
                #   2 hits 10 seconds old > 1 hits 6 seconds old > 3 hits 20 seconds old
                #
                # Sort w/ the highest rated keys first, so we can just eject all those after 9/10ths of
                # maxsize.
                rating		= sorted(
                    (
                        (hits / ( now - last + 1 ), key)		# Avoids hits/0
                        for key,(last,hits) in wrapper._stat.items()
                    ),
                    reverse	= True,
                )
                for rtg,key in rating[maxsize * 9 // 10:]:
                    # log.detail( "{} Ejecting  {!r} == {!r} w/ rating {:7.2f}, stats: {}".format(
                    #     wrapper.__name__, key, wrapper._memo[key], rtg, wrapper._stat[key] ))
                    del wrapper._stat[key]
                    del wrapper._memo[key]
            return entry

        def stats( predicate=None, now=None ):
            """Return the number of memoized data, their average age, and average hits per memoized entry."""
            if now is None:
                now		= timer()
            cnt,age,avg		= 0,0,0
            for key,(last,hits) in wrapper._stat.items():
                if not predicate or predicate( *key ):
                    cnt	       += 1
                    age	       += now-last
                    avg	       += hits
            return cnt,age/(cnt or 1),avg/(cnt or 1)

        wrapper.stats		= stats

        def reset():
            """Flush all memoized data."""
            wrapper._memo	= dict()		# { args: entry, ... }
            wrapper._stat	= dict()		# { args: (<timestamp>, <count>), ... }

        wrapper.reset		= reset

        wrapper.reset()

        return wrapper

    return decorator


#
# @util.retry		-- Retry w/ exponential back-off, 'til truthy result returned
#
def retry( tries, delay=3, backoff=1.5, default_cls=None, log_at=None, exc_at=logging.WARNING ):
    """Retries a function or method until it returns a truthy value.  If default_cls is None, will
    recycle (keep returning) any prior non-falsey value 'til successful again.  Otherwise, will
    return a default_cls instance (or just its falsey value, eg. False) on failure.

    The 'delay' sets the initial delay in seconds, and 'backoff' (defaults to 1.5x; a 50% increase
    in delay each retry) sets the factor by which the delay should lengthen after each
    failure/falsey value.  The 'backoff' multiple must be greater than 1, or else it isn't really a
    backoff.  The 'tries' must be at least 0 to have any exponential effect, and delay greater than
    0; once 'tries' expires, the backoff will remain constant.

    Once truthy, the values reset 'til the next failure.

    """
    if delay <= 0:
        raise ValueError("delay must be greater than 0")
    if backoff <= 1:
        raise ValueError("backoff must be greater than 1")
    if tries < 0:
        raise ValueError("tries must be 0 or greater")

    def decorator( func ):
        @wraps( func )
        def wrapper( *args, **kwds ):
            now			= timer()
            if wrapper.lst is None:
                wrapper.lst	= now
            if wrapper.ok or now >= wrapper.lst + delay * backoff ** min( wrapper.cnt, tries ):
                # Was truthy last time, or it is time to to call again.
                rv		= None
                try:
                    wrapper.lst	= now
                    rv		= func( *args, **kwds )
                except Exception as exc:
                    if exc_at:
                        log.log( exc_at,  f"{wrapper.__name__}: Exception after {wrapper.cnt} {'successes' if wrapper.ok else 'failures'}: {exc}" )
                    if log.isEnabledFor( logging.DEBUG ):
                        logging.debug( "%s", ''.join( traceback.format_exc() ))
                else:
                    if rv:
                        wrapper.rv	= rv
                        return rv
                finally:
                    ok		= bool( rv )
                    if ok != wrapper.ok:
                        # Count resets on rising/falling edge (success <-> failure change)
                        if log_at and log.isEnabledFor( log_at ):
                            log.log( log_at, f"{wrapper.__name__}: Became {'Truthy' if rv else 'Falsey'} after {wrapper.cnt} {'successes' if wrapper.ok else 'failures'}" )
                        wrapper.cnt	= 0		# .cnt resets only on rising/falling edge
                        wrapper.ok	= ok
                    wrapper.cnt += 1			# And *always* counts successes/failures (even on return, just above!)
                # Falls thru on attempt and failure (Falsey)
            wrapper.ok		= False
            if default_cls is None and wrapper.rv:
                return wrapper.rv
            return default_cls() if default_cls else default_cls

        def reset():
            """Force an immediate attempt to run the underlying function, clearing any try count."""
            wrapper.ok		= True		# Start off assuming success (hence no initial delay)
            wrapper.cnt		= 0
            wrapper.lst		= None		# time of last function invocation

        wrapper.reset		= reset

        wrapper.reset()

        return wrapper

    return decorator


def ordinal( num ):
    ordinal_dict		= {1: "st", 2: "nd", 3: "rd"}
    q, mod			= divmod( num, 10 )
    suffix			= q % 10 != 1 and ordinal_dict.get(mod) or "th"
    return f"{num}{suffix}"


def commas( seq, final=None ):  # supply alternative final connector, eg. 'and', 'or'
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
    if final and len(seq) > 1:
        seq			= seq[:-2] + [f"{seq[-2]} {final} {seq[-1]}"]
    return ', '.join( map( str, seq ))


def into_bytes( data: Union[bytes,str] ) -> bytes:
    """Convert hex data w/ optional '0x' prefix into bytes"""
    if isinstance( data, bytes ):
        return data
    if data[:2].lower() == '0x':
        data		= data[2:]
    return bytes.fromhex( data )


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


class mixed_fraction( Fraction ):
    """A Fraction that represents whole multiples of itself as eg. 1+1/2 instead of 3/2"""
    def __str__( self ):
        whole, rest		= divmod( self.numerator, self.denominator )
        if whole and rest:
            return f"{whole}+{Fraction( rest, self.denominator)}"
        return super().__str__()


def remainder_after( proportions, scale=None, total=1 ):
    """Computes the sequence of what fraction must remain, after the preceding proportions have been
    removed.  Avoids scaling unless supplied and not falsey or 1.

    If the desired total to compare each fraction and the sum to isn't 1, supply it.  Also, an
    optional scaling factor for each fraction can be supplied (if the incoming stream of fractions
    don't sum to desired total).

    We support the proportions, scale and total being Fraction and integer values, and producing
    Fraction results.

    """
    f_total			= 0
    for f in proportions:
        if scale and scale != 1:
            f		       *= scale				# (0,total]
        f_starting		= total - f_total		# (0,total]
        f_removed		= f / f_starting		# (0,1]
        f_remaining		= total - total * f_removed     # (0,total]
        yield f_remaining
        f_total		       += f				# (0,total)


def fraction_allocated( reserves, scale=1 ):
    """From a sequence of remainder Fractions, compute the Fraction allocated at each point.

    If the reserves are known to be scaled by some factor, provide it (eg. if they are fixed-point
    fractions, provide the denominator as scale).

    Useful for computing the error between an original sequence of proportions, the resultant
    reserve Fractions, and the final proportion allocated to each party, when the reserve
    fraction is rounded (eg. represented as a fixed-point fraction).

        >>> proportions	= [ 57, 26, 103 ]
        >>> total = sum( proportions )
        >>> total
        186
        >>> reserves = list( remainder_after( proportions, scale=Fraction( 1, total )))
        >>> reserves
        [Fraction(43, 62), Fraction(103, 129), Fraction(0, 1)]
        >>> allocated = list( fraction_allocated( reserves ))
        >>> allocated
        [Fraction(19, 62), Fraction(13, 93), Fraction(103, 186)]

    """
    remaining			= Fraction( 1 )
    for reserve in reserves:
        remaining_after		= remaining * reserve / scale
        yield remaining - remaining_after
        remaining		= remaining_after


def uniq( seq, key=None ):
    """
    Removes duplicate elements from a sequence while preserving the order of the rest.

        >>> list(uniq([9,0,2,1,0]))
        [9, 0, 2, 1]

    The value of the optional `key` parameter should be a function that
    takes a single argument and returns a key to test the uniqueness.

        >>> list(uniq(["Foo", "foo", "bar"], key=lambda s: s.lower()))
        ['Foo', 'bar']
    """
    key				= key or (lambda x: x)
    seen			= set()
    for v in seq:
        k			= key( v )
        if k in seen:
            continue
        seen.add( k )
        yield v


def parse_scutil(input_data):
    """
    A simple parser for the custom 'scutil' data format where every object is a dictionary.
    """
    stack = []
    obj = None

    # Split lines and iterate through them
    for line in input_data.splitlines():
        log.debug( f"Parse: {line}" )
        line = line.strip()
        if not line:
            continue

        if line == '}':
            obj = stack.pop()
            continue

        *key,val = map(str.strip, line.split( ':' ))

        if val.startswith('<') and val.endswith('{'):
            # New dictionary/array detected
            val = {}
            if key:
                stack[-1][key[0]] = val
            stack.append(val)
            continue

        stack[-1][key[0]] = val

    assert not stack, \
        f"Invalid parse: {stack!r}"

    return obj
