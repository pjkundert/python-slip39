
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

import cmath
import codecs
import functools
import logging
import math

from collections	import namedtuple, defaultdict
from typing		import List, Union, Tuple, Optional, Callable

log				= logging.getLogger( __package__ )


def fft( x ):
    """Computes frequency bin amplitude (real) and phase (imaginary) for N/2 frequency bins
    0,..,Nyquist, for an N-sampled signal.

    """
    N				= len( x )
    if N <= 1:
        return x
    even			= fft( x[0::2] )
    odd				= fft( x[1::2] )
    T				= [ cmath.exp( -2j * cmath.pi * k / N ) * odd[k] for k in range( N//2 ) ]
    return [even[k] + T[k] for k in range(N//2)] + \
           [even[k] - T[k] for k in range(N//2)]


def dft( x: List[Union[int, float, complex]] ) -> List[complex]:
    """Takes N either real or complex signal samples, yields complex DFT bins.  Assuming the input
    waveform is filtered to only contain signals in the bandwidth B range -B/2:+B/2 around baseband
    frequency MID, and is frequency shifted (divided by) your baseband frequency MID, and is sampled
    at the Nyquist rate R: given N samples, the result contains N signal frequency component bins:

        index:      0                 N/2-1      N/2      N/2+1       N-1
        baseband:  [MID+] [MID+] ... [MID+]    [MID+/-]  [MID+]  ... [MID+]
        frequency:  DC     1B/N   (N/2-1)B/N   (N/2)B/N  (1-N/2)B/N  -1B/N

    """
    N				= len( x )
    result			= []
    for k in range( N ):
        r			= 0
        for n in range( N ):
            t			= -2j * cmath.pi * k * n / N
            r		       += x[n] * cmath.exp( t )
        result.append( r )
    return result


def idft( y: List[complex] ) -> List[complex]:
    """Inverse DFT on complex frequency bins."""
    N				= len( y )
    result			= []
    for n in range( N ):
        r			= 0
        for k in range( N ):
            t			= 2j * cmath.pi * k * n / N
            r		       += y[k] * cmath.exp( t )
        r		       /= N+0j
        result.append( r )
    return result


def dft_magnitude( bins: List[complex] ) -> List[float]:
    return map( abs, bins )


def dft_on_real( bins: List[complex] ) -> List[float]:
    """Compute the real-valued magnitudes of the provided complex-valued DFT bins.  Since real
    samples cannot distinguish between a +1Hz and a -1Hz signal, the bins assigned to all
    intervening frequencies between the DC and max bins must be combined.

    Only even numbers of bins are supported.  The resultant number of DFT bins is N/2+1, ordered
    from DC to max.

    """
    N				= len( bins )
    assert N % 2 == 0, \
        "Only even numbers of DFT bins are supported, not {len(x)}"
    mags			= list( dft_magnitude( bins ))
    for i in range( 1, N//2 ):
        mags[i]		       += mags[-i]
    return mags[:N//2+1]


if __name__ == "__main__":
    x				= [ 2, 3, 5, 7, 11 ]
    print( "vals:   " + ' '.join( f"{f:11.2f}" for f in x ))
    y				= dft( x )
    print( "DFT:    " + ' '.join( f"{f:11.2f}" for f in y ))
    z				= idft( y )
    print( "inverse:" + ' '.join( f"{f:11.2f}" for f in z ))
    print( " - real:" + ' '.join( f"{f.real:11.2f}" for f in z ))

    N				= 8
    print( f"Complex signals, 1-4 cycles in {N} samples; energy into successive DFT bins" )
    for rot in (0, 1, 2, 3, -4, -3, -2, -1):  # cycles; and bins in ascending index order
        if rot > N/2:
            print( "Signal change frequency exceeds sample rate and will result in artifacts" )
        sig                     = [
            # unit-magnitude complex samples, rotated through 2Pi 'rot' times, in N steps
            cmath.rect(
                1, cmath.pi*2*rot/N*i
            )
            for i in range( N )
        ]
        print( f"{rot:2} cycle" + ' '.join( f"{f:11.2f}" for f in sig ))
        dft_sig                 = dft( sig )
        print( "  DFT:  " + ' '.join( f"{f:11.2f}" for f in dft_sig ))
        print( "   ABS: " + ' '.join( f"{abs(f):11.2f}" for f in dft_sig ))


# class KthLargest(object):
#     """Keep the k largest things."""
#     def __init__(self, K, things):
#         self.window		= list( things )
#         self.K			= K
#         # Transform list x into a heap, in-place, in linear time.
#         heapq.heapify( self.window )
#         while len( self.window ) > K:
# 	    # Pop and return the smallest item from the heap, maintaining the heap invariant. To
# 	    # access the smallest item without popping it, use heap[0].
#             heapq.heappop( self.window )

#     def add( self, val ):
#         """Keep a K-size priority queue (heapq in python), and always make it updated and return the
#         smallest of this group, which will be the k-th large element"""
#         if len( self.window ) < self.K:
#             # Push the value item onto the heap, maintaining the heap invariant
#             heapq.heappush( self.window, val )
#         elif val > self.window[0]:	 # To access the smallest item without popping it, use
#             # heap[0] This heapreplace operation is more efficient than a heappop() followed by
#             # heappush() and can be more appropriate when using a fixed-size heap.
#             heapq.heapreplace( self.window, val )
#         return self.window[0] # To access the smallest item without popping it, use heap[0]


# dB <-> ratio calculations.  Default dB definitions are in terms of
# power.  However, most measured values are of fields (eg. voltages).
dB_type_kwds = {
    'power': {              # eg. Antenna dBi gain
        'base':   10.0,
        'factor': 10.0,
    },
    'field': {              # eg. Amplifier voltage gain
        'base':   10.0,
        'factor': 20.0,
    },
    'sensed':  {            # eg. Loudness sensation gain
        'base':    2.0,
        'factor': 10.0,
    },
}


# dB <-> ratio (for power, by default).  If reference is 1 (default),
# then the value is a ratio.  Otherwise, the 'dB' of the 'value'
# vs. the 'reference' value is computed.  This is the definition of
# dB, so deals in terms of Power (Energy) values by default.
def value_from_dB( dB, reference=1, base=10.0, factor=10.0 ):
    return base ** ( dB / factor ) * reference


def dB_from_value( ratio, reference=1, base=10.0, factor=10.0 ):
    """Convert a ratio [0,oo) into a dB range (-oo,oo), where the ratio 1.0 == 0.0dB.  A -'ve or 0
    is invalid, and tends to -oo (negative infinity).

    """
    if reference and reference != 1:
        ratio			= value / reference
    if ratio > 0:
        return factor * math.log( ratio, base )
    return -math.inf


# dB <-> value (for field values, by default).  This is the practical
# dB, so by default deals in measured values, which are usually Field
# strength measurements (eg. Voltage, Sound Pressure, ...)
def from_dB( dB, reference=1, dB_type='field' ):
    return value_from_dB( dB=dB, reference=reference, **dB_type_kwds[dB_type] )


def into_dB( ratio, reference=1, dB_type='field' ):
    return dB_from_value( ratio=ratio, reference=reference, **dB_type_kwds[dB_type] )


@functools.total_ordering
class dBOrdering(object):
    """Only use self.dB for ordering"""
    def __gt__(self, other):
        return self.dB > other.dB


class Signal( dBOrdering, namedtuple('Signal', [ 'dB', 'offset', 'stride', 'symbols', 'indices' ] )):
    """Provide details on the location of symbols that seem to indicate a reduction in entropy.

    dB:		signal to noise ratio; higher indicates worse entropy (more signal or pattern)
    indices:	a list of offsets of questionable symbols

    """
    def __str__( self ):
        return f"{self.dB:16f}dB, at offset {self.offset:3} x {self.stride:2} bits/symbol for {self.symbols:2} symbols"


def signal_entropy(
    entropy: bytes,
    stride: int			= 8,		# bits per symbol
    symbols: int		= 8,		# symbols per DFT
    overlap: bool		= True,		# sweep across n-1 bits for symbol start
    threshold: float		= 10 / 100,	# Default: allow 10% signal above noise floor?
    middle: Optional[Callable[List[float],float]] = None,  # default to simple average; or eg. statistics.median
) -> Optional[Tuple[float, int]]:
    """Checks for signals in the supplied entropy.  If n-bit symbols are found to exhibit significant
    signal pattern over the median noise, then the pattern will be reported.

    Returns the Signal w/ dB signal multiple by which the greatest signal exceeded the threshold
    noise floor (eg. 10% above the average signal strength), and its bit stride and offset from
    start of entropy.

    Therefore, if a signal is found w/ power above the threshold (0.0dB), it will have a +'ve dB.
    Acceptable (low signal strength == high entropy) signals below the threshold will have a -'ve
    dB.

    So, the result can be sorted by greatest power, and if any power is found to be > 0.0dB, the
    entropy can be rejected as having too much "signal" vs "noise" (entropy).
    """
    entropy_hex			= codecs.encode( entropy, 'hex_codec' ).decode( 'ascii' )
    entropy_bin			= ''.join( f"{int(h,16):0>4b}" for h in entropy_hex )
    length			= len( entropy_bin )

    strongest			= None
    for symb in range(0, length - symbols * stride + 1, stride ):
      for slip in range( stride if overlap else 1 ):  # noqa: E111
        offset			= symb + slip
        bits			= [
            entropy_bin[off:off+stride]
            for off in range( offset, length - stride, stride )
        ][:symbols]
        if len( bits ) < symbols or len( bits[-1] ) < stride:
            break
        # We got a full 'symbols' worth of 'stride' symbol data.  Scale and DFT, and get real-valued bin magnitudes
        raws			= [ int( b, 2 )  for b in bits ]
        sigs			= [ r - 2**(stride-1) for r in raws ]
        dfts			= dft( sigs )
        mags			= dft_on_real( dfts )  # abs energy bins, from DC to max freq

        # print( "bits: " + ' '.join( f"{b:{stride}}" for b in bits ))
        # print( "raws: " + ' '.join( f"{r:{stride}}" for r in raws ))
        # print( "sigs: " + ' '.join( f"{s:{stride}}" for s in sigs ))

        # See if we can observe any signal/noise ratio on any frequency
        # print( "dfts: " + ' '.join( f"{d:{stride}.1f}" for d in dfts ))
        # print( "mags: " + ' '.join( f"{m:{stride}.1f}" for m in mags ))

        top			= max( mags )
        if middle is None:
            mid			= sum( mags ) / len( mags )
        else:
            mid			= middle( mags )
        target			= mid + mid * threshold;
        # Compute dB SNR vs. target.  If all mags are 0 (all sigs were 0), then top and target will
        # all be 0.  However, this means that the signal is totally predictable (contains infinitely
        # strong signal), so pick an small but non-passing snr (1.0 == 0.0dB), so that any other
        # more "legitimate" non-passing signals will likely be chosen as strongest.
        snr			= ( top / target ) if target else 1.0
        snr_dB			= into_dB( snr )
        signal			= Signal( dB=snr_dB, offset=offset, stride=stride, symbols=symbols, indices=[] )
        if strongest is None or signal > strongest:
            strongest		= signal
            print( f"strongest signal: {strongest}" )
    return strongest


def shannon_entropy(
    entropy: bytes,
    stride: int			= 8,		# bits per symbol
    overlap: bool		= True,
    threshold: float		= 10/100,	# Allow up to 10% bits-per-symbol entropy deficit
    snr_min: float		=  1/100,	# Minimum snr .01 == -40dB
) -> Optional[str]:
    """Estimates the "Symbolised Shannon Entropy" for stride-bit chunks of the provided entropy; by
    default, since we don't know the bit offset of any pattern, we'll scan at each possible bit
    offset (overlap = True).

    We'll return the estimated predictability of the entropy, in the range [0,1], where 0 is
    unpredictable (high entropy), and 1 is totally predictable (no entropy), but as a dB range,
    where -'ve dB is below the threshold and acceptable, and +'ve is above the predictability
    threshold, and is unacceptable.

    The "strongest" (least entropy, most predictable, most indicative that the entropy is
    unacceptable) signal will be returned.

    See: https://www.sciencedirect.com/topics/engineering/shannon-entropy

    """
    entropy_hex			= codecs.encode( entropy, 'hex_codec' ).decode( 'ascii' )
    entropy_bin			= ''.join( f"{int(h,16):0>4b}" for h in entropy_hex )

    # Find all the unique n-bit symbols in the entropy at the desired offset(s)
    strongest			= None
    for offset in range( 1 if overlap else stride ):
        # Calculate the frequency of each unique symbol
        frequency		= defaultdict( float )
        # How many full n-bit symbols fit in the entropy at the current symbol-start offset?
        symbols			= ( len( entropy_bin ) - offset ) // stride
        for s in range( symbols ):
            i			= offset + s * stride
            symbol		= entropy_bin[i:i+stride]
            frequency[symbol]  += 1 / symbols
        assert .999 <= sum( frequency.values() ) <= 1.001, \
            f"Expected 1.0 sum of probabilities events, found {frequency!r}"
        assert all( len( s ) == stride for s in frequency ), \
            f"Expected all {stride}-bit symbols, found {frequency!r}"

        bitspersymbol			= -sum(  # sum may range: (~-0.0,...)
            probability * math.log( probability, 2 )
            for probability in frequency.values()
        )
        # For small numbers of symbols, we cannot achieve a full N unique samples.  Therefore, the
        # number of "bits of entropy" per symbol will be low -- even if all of the samples obtained
        # are unique.  Therefore, we return a value in the range (0=bad,1=good) scaled by the bits
        # required to encode the maximum number of unique symbols possible (due to the symbol or
        # entropy size), not in the range [0,2^stride].
        shannon			= 0.0
        N			= min( symbols, 2**stride )
        if N > 1:
            shannon		= bitspersymbol / math.log( N, 2 )

        # So now, shannon is 1.0 for a "good" perfectly unpredictable entropy (all symbols
        # different, full bits-per-symbol required to encode), and 0 for "bad" perfectly predictable
        # entropy (all symbols identical, zero bits-per-symbol to encode).  This is the inverse of
        # what we want: the more predictable something is, the stronger the "signal" is vs. the
        # noise (entropy).  A 10% threshold means "I want at most 10% predictability; I want 90%
        # noise".  This
        predictability		= 1 - shannon			# 0 ==> good entropy, 1 ==> no entropy

        # We want a -'ve dB if below (low predictability, good entropy, acceptable), +'ve if
        # at/above threshold (high predictability, too much signal, reject).  1.0x == 0.0dB.
        # However, we'll typically often see good, high-entropy data which turns out to have a
        # shannon == 1.0, implying a predictability == 0, yielding an snr ratio of 0, which is
        # invalid (tends to -oo).  We want to avoid this.  We know that the range is predictability
        # range is (0,1), and we'll typically allow a threshold of 10%, so 0 is not -oo!  We really
        # want to map (0...threshold,...1) onto a ratio range like .01 (-40dB) to 100 (+40dB), with
        # 1.0 == 0dB right at threshold.  Map the range (0,threshold] to (.01,1] (mapped to -'ve
        # dB), and let the +'ve dB (threshold,1) range fall where it may.  For example, if threshold
        # is .1 and predictability is also .1, we want to map that to exactly 1.0:
        #
        #             predictability
        #             v
        #     1/100 + 0    / ( .1 / ( 1 - 1/100 )) == 0.0100 == -10.0   dB  # -'ve below threshold: 
        #     1/100 + .043 / ( .1 / ( 1 - 1/100 )) == 0.4357 ==  -7.216 dB  #
        #     1/100 + .1   / ( .1 / ( 1 - 1/100 )) == 1.0000 ==   0.0   dB  # exactly at threshold
        #     1/100 + 1    / ( .1 / ( 1 - 1/100 )) == 9.9100 ==  19.20  dB  # +'ve above threshold
        # 
        assert threshold > 0, \
            "A small +'ve ratio threshold of Shannon entropy deficit > 0 is required eg. 10%, not {threshold=:7.2f}"
        snr			= snr_min + predictability / ( threshold / ( 1 - snr_min ))
        snr_dB			= into_dB( snr )
        signal			= Signal( dB=snr_dB, offset=offset, stride=stride, symbols=symbols, indices=[] )

        log.warning( f"Found {len(frequency):3} unique (of {2**stride:5} possible) in {symbols:3}" 
                     f"x {stride:2}-bit symbols at offset {offset:2} in {len(entropy_bin):4}-bit entropy:"
                     f" Shannon Entropy {bitspersymbol:7.3f} b/s, P({shannon:7.3f}) unpredictable; {predictability=:7.3f}"
                     f"vs. {threshold=:7.3f} ==  {snr=:7.3f} (w/ {snr_min=:7.3f}, {1-snr_min=:7.3f}, {threshold/(1-snr_min)=:7.3f} {predictability/(threshold/(1-snr_min))=:7.3f}) ==> {snr_dB:7.3f}dB: {entropy_hex}" )

        if strongest is None or signal > strongest:
            strongest		= signal
            print( f"strongest shannon: {strongest}" )
    return strongest


def analyze_entropy(
    entropy: bytes,
) -> Optional[str]:
    """Analyzes the provided entropy.  If patterns are found, reports the findings."""
    for stride in range( 2, 16 ):
        shannon			= shannon_entropy( entropy, stride=stride )
    return None
