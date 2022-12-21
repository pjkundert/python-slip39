import json
import logging
import pytest
import time

from fractions		import Fraction as F
from functools		import wraps
from collections	import defaultdict

from .util		import remainder_after, retry, timer, ordinal

log				= logging.getLogger( 'util_test' )


def test_remainder_after():
    assert list( remainder_after( [ .25, .25, .25, .25 ] )) == pytest.approx( [.75, 2/3, 1/2, 0] )
    # Now, the last segment requires double the remainder; so it extends -1x past the end...
    assert list( remainder_after( [ .25, .25, .25, .50 ] )) == pytest.approx( [.75, 2/3, 1/2, -1] )

    # Now, try some more complex Fractions, with differing desired total (eg. parts in 10,000), and
    # scale (multiplication factor required of each fraction to sum to desired total).

    parts			= [
        F( 1,  4 ),     # 3/12
        F( 1,  3 ),     # 4/12
        F( 1,  6 ),     # 2/12
        F( 1, 12 ),     # 1/12
        F( 1,  6 ),     # 2/12
    ]                  # 12/12
    assert sum( parts ) == 1
    assert list( remainder_after( parts )) == [
        F( 3, 4 ),
        F( 5, 9 ),
        F( 3, 5 ),
        F( 2, 3 ),
        0
    ]

    percs			= [
        f * 100 for f in parts
    ]
    assert sum( percs ) == 100
    assert list( remainder_after( percs, total=100 )) == [
        F( 75, 1 ), F( 500, 9 ), F( 60, 1 ), F( 200, 3 ), 0
    ]

    # Now, go straight from the ratio (0,1] to the parts in 10,000
    assert list( remainder_after( parts, scale=10000, total=10000 )) == [
        F( 7500, 1 ), F( 50000, 9 ), F( 6000, 1 ), F( 20000, 3 ), 0
    ]
    assert list( map( int, remainder_after( parts, scale=10000, total=10000 ))) == [
        7500, 5555, 6000, 6666, 0
    ]

    # If we're working entirely in Fractions and integers, make certain our results remain in
    # Fractions.  Lets make our proportions in range (0,1] as fixed-point x 2^16, and support
    # proportions that sum to something other than 1.  Since we are dealing in the *remainder*
    # (after sending the proportion to a recipient, in no case will a remainder ever equal 1, so we
    # don't have to worry about representing the range (0,1) in our outputs -- only (0,1].  Hence,
    # our denominator can be the full bit-width of the unsigned value.
    for factor in [ 1, 5, F( 99 / 100 ), F( 101, 100 )]:
        parts_factor		= [
            f * factor for f in parts
        ]
        rem_uint16		= list( remainder_after(
            parts_factor,
            scale	= ( 2 ** 16) / sum( parts_factor ),
            total	= ( 2 ** 16),
        ))
        assert rem_uint16 == [
            F(  49152, 1 ),
            F( 327680, 9 ),
            F( 196608, 5 ),
            F( 131072, 3 ),
            F(      0, 1 ),
        ]
        # And, sure enough, after correcting for our 2**16-1 scale, we get the originally calculated Fractions
        assert [
            f / ( 2 ** 16 ) for f in rem_uint16
        ] == [
            F( 3, 4 ),
            F( 5, 9 ),
            F( 3, 5 ),
            F( 2, 3 ),
            0
        ]


def exception_every( N=2, extra=0 ):
    if hasattr( extra, '__iter__' ):
        extra		= iter( extra )

    def decorator( func ):
        @wraps( func )
        def wrapper( *args, **kwds ):
            if wrapper.num > 0:
                wrapper.num    -= 1
                raise AssertionError( f"Fail for {wrapper.num} more times" )
            wrapper.nth	       += 1
            if wrapper.nth % N == 0:
                wrapper.num	= next( extra ) if hasattr( extra, '__next__' ) else extra
                raise AssertionError( f"Fails on {ordinal(wrapper.nth)} try, for {wrapper.num} more times" )
            return func( *args, **kwds )

        wrapper.nth		= 0
        wrapper.num		= 0

        return wrapper

    return decorator


def test_retry():
    """Lets target a backoff of 1.5x, and confirm at least 90% of that occurs.

    This is timing related, so we may have to make this an XFAIL test...

    """
    backoff			= 1.5

    @retry( 5, delay = .1, backoff = backoff, log_at = logging.DEBUG, exc_at=logging.INFO )
    @exception_every( 2, extra=range( 10 ))
    def truthy():
        truthy.i	       += 1
        return truthy.i

    truthy.i			= 0

    results			= {}
    dur				= 0.05
    now = then 			= timer()
    for i in range( 98 ):
        ela			= i * dur
        time.sleep( max( 0, ela - (now - then )))
        results[f"{ela:6.4f}s"] = truthy()
        now			= timer()

    log.debug( json.dumps( results, indent=4 ))

    counts			= defaultdict( int )

    for v in results.values():
        counts[v]	       += 1

    log.debug( json.dumps( counts, indent=4 ))

    for k in counts.keys():
        if k-1 in counts:
            log.info( f" {k} vs {k-1}: {counts[k]/counts[k-1]:7.3f}x" )
            # Expected exponential backoff w/ increasing failures
            assert counts[k] > counts[k-1] * backoff * 90/100
