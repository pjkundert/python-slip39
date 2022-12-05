import json
import logging
import pytest
import time

from functools		import wraps
from collections	import defaultdict

from .util		import remainder_after, retry, timer, ordinal

log				= logging.getLogger( 'util_test' )


def test_remainder_after():
    assert list( remainder_after( [ .25, .25, .25, .25 ] )) == pytest.approx( [.75, 2/3, 1/2, 0] )
    # Now, the last segment requires double the remainder; so it extends -1x past the end...
    assert list( remainder_after( [ .25, .25, .25, .50 ] )) == pytest.approx( [.75, 2/3, 1/2, -1] )


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
