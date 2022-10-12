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

import cmath
import codecs
import logging
import math

try:
    from numpy		import fft as np_fft
except ImportError:
    np_fft			= None

from collections	import namedtuple, defaultdict
from typing		import List, Union, Tuple, Optional, Callable, Sequence

from ..util		import mixed_fraction, ordinal, commas, is_power_of_2, avg, rms

log				= logging.getLogger( __package__ )


def fft( x ):
    """Computes frequency bin amplitude (real) and phase (imaginary) for N/2 frequency bins
    0,..,Nyquist, for an N-sampled signal.  Uses numpy.fft.fft if available, otherwise, pfft where N
    is a power of 2, dft for other N.

    """
    if np_fft:
        return [ complex(b) for b in np_fft.fft( x ) ]
    N				= len( x )
    if not is_power_of_2( N ):
        return dft( x )
    return pfft( x )


def ifft( y: List[complex] ) -> List[complex]:
    """Compute inverse FFT for any complex bins N (ideally a power of 2, or multiple of 2."""
    if np_fft:
        return [ complex(s) for s in np_fft.ifft( y ) ]
    return idft( y )


def pfft( x ):
    """A simple pure-python FFT"""
    N				= len( x )
    if N <= 1:
        return x
    even			= pfft( x[0::2] )
    odd				= pfft( x[1::2] )
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
    """Inverse DFT on complex frequency bins.  Very slow O(N^2), so use ... carefully.

    Since we're likely to use this a lot for the same values of N, we'll memoize the constants we
    use for multiplying.

    """
    N				= len( y )
    #assert N <= 170, f"idft: {N=} too large."  # 512-bit entropy as 3-bit symbols
    e_sk_N			= idft.e_sk.setdefault( N, [] )
    if e_sk_N:
        e_sk_N_i		= iter( e_sk_N )
        result			= [
            sum(
                y_k * e_sk
                for y_k,e_sk in zip( y, e_sk_N_i )
            ) / N+0j
            for n in range( N )
        ]
    else:
        #print( f"idft: Memoizing {N=} multiplication factors" )
        result			= []
        for n in range( N ):
            r			= 0
            s			= 2j * cmath.pi * n / N
            for k in range( N ):
                e_sk		= cmath.exp( s * k )
                e_sk_N.append( e_sk )
                r	       += y[k] * e_sk
            r		       /= N+0j
            result.append( r )
    return result
idft.e_sk			= {}  # noqa: E305


def dft_magnitude( bins: Sequence[complex] ) -> List[float]:
    return [ abs( b ) for b in bins ]


def dft_normalize( bins: Sequence[complex] ) -> List[float]:
    N				= len( bins )
    assert N % 2 == 0, \
        "Only even numbers of DFT bins are supported, not {len(x)}"
    scale			= math.log( N, 2 )
    return [ b / scale for b in bins ]


def dft_to_rms_mags( bins: List[complex] ) -> List[float]:
    """Compute the real-valued magnitudes of the provided complex-valued DFT bins.  Since real samples
    cannot distinguish between a +1Hz and a -1Hz signal, the bins assigned to all intervening
    frequencies between the DC and max bins must be combined.

    Only even numbers of bins are supported.  The resultant number of DFT bins is N/2+1, ordered
    from DC to max.

    And, while we're at it, we'll normalize the scale so that DFTs of one number of bins is
    comparable to another; they are scaled at a rate of sqrt(N).  This makes the RMS energy and
    magnitudes on DFTs of different sizes comparable with eachother.

    """
    N				= len( bins )
    mags			= dft_magnitude( bins )
    norm			= dft_normalize( mags )
    nrms			= rms( norm )
    for i in range( 1, N//2 ):
        norm[i]		       += norm[-i]
        norm[-i]		= 0.0
    return nrms, norm[:N//2+1]


def dft_on_real( bins ):
    nrms, mags			= dft_to_rms_mags( bins )
    return mags


def denoise_mags( mags, threshold, middle=None, stride=8 ):
    """Look for top signals within the given magnitudes.  This involves finding a noise floor within the
    magnitude bins w/ a signal level threshold x above the noise floor.  We'll compute the SNR of
    each signal by iteratively scaling the largest signals down to the average, and then look for
    new signals that have risen above the new (lower) noise-floor avg.  Stops when the remaining
    bins are below the avg * threshold.

    Returns the noise threshold target, and list of the top mags: (target, [ (snr,index), ... ])

    """
    snrs			= set()
    curs			= mags[:]
    cavg			= avg( curs ) if middle is None else middle( curs )
    target			= cavg * threshold
    while peaks := set(
            i
            for i,m in enumerate( curs )
            if i not in snrs and m >= target
    ):
        # There are 1 or more new peaks above the middle curs 'cavg' value.  Note that they are
        # candidate signals in snrs.
        snrs.update( peaks )
        # Replace each signal with the current cavg * threshold 'target'.  This lowers the "avg"
        # noise level by removing the signal portion of the now recognized signal bins; only the
        # remaining non-signal portion of the signal candidate bins and the remaining non-gisnal
        # bins influence the new cavg.
        curs			= [
            target if i in snrs else b
            for i, b in enumerate( mags )
        ]
        cavg			= avg( curs ) if middle is None else middle( curs )
        target			= cavg * threshold
        #print( f"dnoi: {' '.join( f'{c:{stride}.1f}({mags[i] / target:{stride-2}.1f})' for i,c in enumerate( curs ))}: {target=:7.1f}" )

    # Return the noise threshold target magnitude deduced, and the index,SNR for each signal bin,
    # sorted by SNR
    return target, sorted( ( (i, mags[i] / target) for i in snrs ), key=lambda e: e[1], reverse=True )


def signal_recover_real( dfts, scale=None, integer=False, amplify=None ):
    """Recover a real signal from the provided DFT output.  Optionally, scale the DFT before
    recovering the signal.  Optionally, round the values to integer (eg. if the original signal was
    integer).

    """
    #print( "dfts: " + ' '.join( f"{d:{stride*2}.1f}" for d in dfts ))
    assert scale in (None, 0, 1) or scale % 2 == 0, \
        f"Only even multiples of a DFT are valid, not x{scale}"
    while ( scale or 1 ) >= 2:
        scale		      //= 2
        N			= len( dfts )
        # When doubling the length of a DFT, we have to scale each entry by 2x
        dfts			= [d*2 for d in dfts]
        # Insert N entries in the middle
        dfts			= dfts[:N//2] + [0j] * N + dfts[N//2:]
        # Split the high-frequency bin from the old DFT between the 2 new lower frequency bins.  Was
        # in position [N//2+1], or also [-N//2]; now is stil in the position [-N//2], since N is
        # still the old DFT size!  The corresponding location is at dft[N//2]; this will always be a
        # freshly added 0+0j bin.
        dfts[-N//2]	       /= 2
        dfts[N//2]	       += dfts[-N//2]
    #print( "dfts: " + ' '.join( f"{d:{stride*2}.1f}" for d in dfts ))
    sigR			= ifft( dfts )
    #print( "sigR: " + ' '.join( f"{s:{stride*2}.1f}" for s in sigR ))
    sigR			= [ s.real for s in sigR ]
    #print( "sigR: " + ' '.join( f"{s:{stride*2}.1f}" for s in sigR ))
    if amplify:
        sigR			= [s * amplify for s in sigR]
    if integer:
        sigR			= list( map( int, map( round, sigR )))
        #print( "sigR: " + ' '.join( f"{s:{stride*2}}" for s in sigR ))
    return sigR


def signal_draw( s, scale=None, neg=None, pos=None ):
    """Draws a single-line signed waveform if pos/neg is None, or the +'ve/-'ve half
    of a waveform.  Default scale is 1 signed byte.

        default:    "'‾~_.,._~‾'
        pos:                     ,._~‾'"'‾~_.,
        neg:        "'‾~_.,._~‾'"

    """
    if neg is True or pos is False:
        return " \"'‾~_.,"[max( -1, min( 6, int( (-s-1) * 7 // ( scale or 128 )))) + 1]
    elif pos is True or neg is False:
        return " ,._~‾'\""[max( -1, min( 6, int(   s    * 7 // ( scale or 128 )))) + 1]
    else:
        return ",._~‾'\"" [max( -3, min( 3, round( s    * 7  / ( scale or 256 )))) + 3]


if __name__ == "__main__":
    x				= [ 2, 3, 5, 7, 11 ]
    print( "vals:   " + ' '.join( f"{f:11.2f}" for f in x ))
    y				= fft( x )
    print( "DFT:    " + ' '.join( f"{f:11.2f}" for f in y ))
    z				= ifft( y )
    print( "inverse:" + ' '.join( f"{f:11.2f}" for f in z ))
    print( " - real:" + ' '.join( f"{f.real:11.2f}" for f in z ))

    N				= 8
    print( f"Complex signals, 1-4 cycles in {N} samples; energy into successive DFT bins" )
    for rot in (0, 1, 2, 3, -4, -3, -2, -1):  # cycles; and bins in ascending index order
        if rot > N/2:
            print( "Signal change frequency exceeds sample rate and will result in artifacts" )
        sigs                    = [
            # unit-magnitude complex samples, rotated through 2Pi 'rot' times, in N steps
            cmath.rect(
                1, cmath.pi*2*rot/N*i
            )
            for i in range( N )
        ]
        print( f"{rot:2} cycle" + ' '.join( f"{f:11.2f}" for f in sigs ))
        dfts                    = fft( sigs )
        print( "  DFT:  " + ' '.join( f"{f:11.2f}" for f in dfts ))
        print( "   ABS: " + ' '.join( f"{abs(f):11.2f}" for f in dfts ))


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
        ratio		       /= reference
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


class Signal( namedtuple('Signal', [ 'dB', 'stride', 'symbols', 'offset', 'details' ] )):
    """Provide details on the location of symbols that seem to indicate a reduction in entropy.

    dB:		signal to noise ratio; higher indicates worse entropy (more signal or pattern)
    details:	A textual description of the signal
    """
    def __str__( self ):
        return f"{self.dB:7.2f}dB, at {self.offset=:3}: {self.symbols:2} x {self.stride:2} bits/symbol: {self.details}"


def entropy_bin_ints( entropy_bin, offset, symbols, stride, cancel_dc=None ):
    length			= len( entropy_bin )
    bits			= [
        entropy_bin[off:off+stride]
        for off in range( offset, length - stride + 1, stride )
    ][:symbols]
    ints			= [ int( b, 2 )  for b in bits ]
    if cancel_dc:
        ints			= [ r - 2**(stride-1) for r in ints ]
    # print( "bits: " + ' '.join( f"{b:{stride*2}}" for b in bits ))
    # print( "ints: " + ' '.join( f"{r:{stride*2}}" for r in ints ))
    return ints


def entropy_bin_dfts( entropy_bin, offset, symbols, stride, cancel_dc=True ):
    """Compute the frequency bin magnitudes for 'stride'-bits x symbols starting at bit 'offset'.
    If cancel_dc, shifts the numeric zero from bit value '00...' to '10...'; if the values are
    randomly distributed, the DC offset should be cancelled out.

    """
    sigs			= entropy_bin_ints( entropy_bin, offset=offset, symbols=symbols, stride=stride,
                                                    cancel_dc=cancel_dc )
    #print( "sigs: " + ' '.join( f"{s:{stride*2}}" for s in sigs ))
    dfts			= fft( sigs )

    # See if we can observe any signal/noise ratio on any frequency
    #print( "dfts: " + ' '.join( f"{d:{stride*2}.1f}" for d in dfts ))
    return dfts


def int_decode( c, stride=8 ):
    """Output the decimal (if possible) and decoded view of the integer datum 'c'"""
    if stride == 6:  # base-64 URL-safe
        return f"{'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'[c]:<{stride}}"
    if stride == 5:  # base-32
        return f"{'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'[c]:<{stride}}"
    if stride == 4:  # hex nibbles
        return f"x{'0123456789ABCDEF'[c]:<{stride-1}}"
    if stride == 3:  # octal digits
        return f"o{'01234567'[c]:<{stride-1}}"
    if 1 <= stride <= 2:  # bits / base-4
        return f"{'0123'[c]:<{stride}}"
    if stride <= 8 and 32 <= c < 127:
        s		= ("'" + chr( c ) + "'")
        return f"{s:<{stride}}"
    hex			= f"{c:0{(stride+3)//4}X}"
    return f"{hex:<{stride}}" if stride <= len( hex ) + 2 else f"0x{hex:<{stride-2}}"


def signal_entropy(
    entropy: bytes,
    stride: int			= 8,		# bits per symbol
    symbols: Optional[int]	= None,		# symbols per DFT; default to ~128 bits and a power of 2, but < length
    overlap: bool		= False,        # sweep across n-1 bits for symbol start
    threshold: Optional[float]	= None,		# Default: must be a known length/stride/symbols
    ignore_dc: bool		= False,        # For eg. character data, we know there'll be a big DC component
    show_details: bool		= True,		# include signal details (incl. expensive ifft)
    middle: Optional[Callable[List[float],float]] = None,  # default to normalized RMS energy, or eg. statistics.median on bin magnitudes
    harmonics_max: int		= 2,		# maximum harmonics to represent
) -> Optional[Tuple[float, int]]:
    """Checks for signals in the supplied entropy.  If n-bit 'stride' or 'base'-n symbols are found
    to exhibit significant signal pattern over the average noise, then the pattern will be reported.

    Returns the Signal w/ dB signal multiple by which the greatest signal exceeded the threshold
    noise floor (defaults to RMS average energy), and its bit stride and offset from start of
    entropy.

    Therefore, if a signal is found w/ power above the threshold (0.0dB), it will have a +'ve dB.
    Acceptable (low signal strength == high entropy) signals below the threshold will have a -'ve
    dB.  Using something like statistics.median is problematic for low-noise signals, because if a
    sufficient number of bins have 0 energy, the noise will be 0, and a "default" SNR (signal/noise
    *ratio*) of 1.0 will be used (0.0 dB), allowing any more legitimate signal to be used instead of
    the unlikely "perfect" noise-free signal.

    So, the result can be sorted by greatest power, and if any power is found to be > 0.0dB, the
    entropy can be rejected as having too much "signal" vs "noise" (entropy).

    """
    entropy_hex			= codecs.encode( entropy, 'hex_codec' ).decode( 'ascii' )
    entropy_bin			= ''.join( f"{int(h,16):0>4b}" for h in entropy_hex )
    length			= len( entropy_bin )
    assert not overlap or not ignore_dc, \
        "Cannot specify both overlap and ignore_dc (intended for handling fixed-location symbols)"
    if symbols is None:
        # Default to the largest even-numbered amount of symbols that will fit in the signal, except
        # if 'overlap' is specified, ensure we sweep across all bit-offsets of the symbol once.
        symbols			= length // ( stride * 2 ) * 2
        if overlap and length - symbols * stride < stride - 1:
            symbols	       -= 2
    assert symbols // 2 * 2 == symbols, \
        f"An even number of symbols must be specified, not {symbols=}"
    assert symbols * stride <= length, \
        f"{symbols} x {stride}-bit symbols is beyond signal {length=}"
    if threshold is None:
        threshold		= signal_entropy.signal_limits.get(
            overlap, {} ).get(
                length, {} ).get(
                    stride, {} ).get(
                        symbols )
    assert threshold and ( 0 < threshold ), \
        f"A small +'ve ratio threshold of Signal energy (0,...) is required for {length}-bit entropy w/ {stride}-bit symbols eg. 300%, not {threshold=!r}"
    #print( f"signal_entropy: {length:3}-bit entropy w/ {symbols:3} x {stride:2}-bit symbols ({ignore_dc=:5}): {threshold=:f}" )
    dc				= 0+0j
    strongest			= None
    mags_all			= []
    for symb in range(0, length - symbols * stride + 1, stride ):
        for slip in range( stride if overlap else 1 ):  # noqa: E111
            offset		= symb + slip
            #print( f"=> {symb=:3} + {slip=:3} == {offset}" )
            if length - offset < symbols * stride:
                break
            dfts		= entropy_bin_dfts( entropy_bin, offset, symbols, stride, cancel_dc=not ignore_dc )
            #print( f"dfts: {' '.join( f'{b:{stride*2}.1f}' for b in dfts )}" )
            dc			= dfts[0]
            if ignore_dc:
                dfts[0]		= 0+0j
            nrms, mags		= dft_to_rms_mags( dfts )  # abs energy bins, from DC to max freq
            mags_all.append( mags )
            #print( f"mags: {' '.join( f'{m:{stride*2}.1f}' for m in mags )}: {sum(mags):7.2f} sum, {avg(mags):7.2f} avg, {nrms:7.2f} RMS; dc: {dc:11.1f} == {abs(dc):7.2f} abs" )
            target, snrs	= denoise_mags( mags, threshold )
            snrd		= dict( snrs )  # i: snr
            #print( f"snrs: {' '.join( f'{snrd[i]:{stride*2}.1f}' if i in snrd else (' ' * stride*2) for i in range( len( mags )))}: {target=:7.1f}" )

            # mid			= nrms if middle is None else middle( mags )
            # target		= mid * threshold
            # # Find the magnitude, offset of the top magnitudes exceeding target, sorted high to low
            # tops		= sorted( ( (m,i) for i,m in enumerate( mags ) if m > target ), reverse=True )
            # # Compute total signal dB SNR vs. target.  If all mags are 0 (all sigs were 0), then top
            # # and target will all be 0.  However, this means that the signal is totally predictable
            # # (contains infinitely strong signal), so pick an small but non-passing snr (1.0 ==
            # # 0.0dB), so that any other more "legitimate" non-passing signals will likely be chosen
            # # as strongest.  If no signal; report how far below the target our strongest bin is.

            # When we have multiple signals, a Signal with several strong signals should have an SNR
            # higher than something with fewer/weaker signals.  However, only the portion *above*
            # the target threshold count.  So, sum the tops, and compute the overall Signal SNR.
            if snrd:
                peak		= target + sum( mags[i] - target for i in snrd )
            else:
                peak		= max( mags )  # No signals; SNR is greatest bin vs. threshold target
            snr			= ( peak / target ) if target else 1.0
            snr_dB		= into_dB( snr )
            #print( f"tops: {offset=:3}, {peak=:7.2f}, {threshold=:7.2f}, {target=:7.2f}, {snr=:7.2f}, {snr_dB=:7.2f}" )
            if strongest and snr_dB <= strongest.dB:
                continue
            if snr_dB < 0 or not show_details:
                strongest	= Signal( dB=snr_dB, stride=stride, symbols=symbols, offset=offset, details='' )
                continue

            # Find the strongest signal frequency bin.  The max frequency (last) bin indicates some
            # pattern sensed in every second symbol (the Nyquist rate, sampled at 2x the max
            # frequency detectable).  The min frequency (first) bin indicates a DC offset (symbol
            # values not centered around zero).  For N symbols, there are N/2+1 bins, [DC], [min],
            # ..., [max]: the intervening N/2 bins [min], ..., [max] contain evenly spaced
            # frequencies; eg. for N==8, N/2+1==5 bins, N/2==4 min-max bins where:
            #
            #     For symbols ==  8 ==>  64 bits 	For symbols == 16 ==> 128 bits
            #     ------------------------------        ------------------------------
            #     [0](DC)  ==> 8*8== 64 bits/beat       [0](DC)  ==>16*8==128 bits/beat
            #     [1](min) ==> 4*8== 32 bits/beat       [1](min) ==> 8*8== 64 bits/beat
            #     [2]          3*8== 24                 [2]          7*8== 56
            #     [3]          2*8== 16                 [3]          6*8== 48
            #     [4](max) ==> 1*8==  8 bits/beat       [4]          5*8== 40
            #                                           [5]          4*8== 32
            #                                           [6]          3*8== 24
            #                                           [7]          2*8== 16
            #                                           [8](max) ==> 1*8==  8 bits/beat
            #

            # Draw the signal area of interest over 'symbols' of the 'stride'-bit symbols beginning at bit 'offset'.
            details		= '\n'
            offpref		= ''
            if offset > 8:
                details	       += f"...x{offset:<3}>{entropy_bin[offset:]}\n"
                offpref		= ' ' * 8
            else:
                details	       += f"{entropy_bin}\n"
                offpref		= ' ' * offset
            details	       += offpref + ''.join(
                '-_'[(( i-offset ) // stride ) % 2] if ( offset <= i < ( offset + symbols * stride )) else ' '
                for i in range( offset, length )
            ) + '\n'

            if stride >= 4:
                details	       += offpref + ''.join(
                    f"{c:<{stride}}"
                    for c in entropy_bin_ints( entropy_bin, offset=offset, symbols=symbols, stride=stride, cancel_dc=not ignore_dc )
                ) + ' decimal\n'
            details	       += offpref + ''.join(
                int_decode( c, stride=stride )
                for c in entropy_bin_ints( entropy_bin, offset=offset, symbols=symbols, stride=stride )
            ) + f" base-{2**(4 if stride >= 7 else stride)}" + ("/ASCII" if stride >= 7 else "") + " decoding\n"

            # Select the one or two highest energy harmonics, and scale the waveform (which is
            # denominated in stride-bit chunks) to the extent needed to cover the binary version of the
            # entropy (then decimate to fit exactly).  So, if the 8-bit signal values are being
            # recovered, we can scale the waveform by 8x.  Also, scale the amplitude by the (removed) DC
            # component; this counteracts the reduction in dynamic range inherent to typical ASCII
            # values (eg. the digits 0-9 are only 8% of the full ASCII range).
            dfts_rec		= [0+0j] * len( dfts)
            harmonic		= []
            for max_i in snrd:
                if harmonics_max and harmonic and len( harmonic ) >= harmonics_max:
                    break
                # The 0'th bin is DC, 1st is the base frequency, and then for eg. 16 symbols, we get
                # DC + 8 bins, where each bin represents a harmonic frequency component repeating
                # every 16/1==16, 16/2==8, 16/3==5+1/3, 16/4==4, 16/5==3+1/5, ..., 16/8==2 (the max
                # Nyquist frequency) symbols.
                harmonic.append( max_i )
                dfts_rec[max_i]	= dfts[max_i]
                if 0 < max_i < len(mags)-1:
                    dfts_rec[-max_i] = dfts[-max_i]		# ... and its symmetrical bin, if not max freq.
            harmonic_freq	= [
                mixed_fraction( len( dfts ), h )
                for h in harmonic
                if h > 0
            ]

            dc_amplify		= None
            if ignore_dc:
                # scale the signal by the ratio of the removed DC to the largest other signal.  Since we know that
                # the other signals were DC "higher" in the original signal, amplifying the signal by this ratio
                # shouldn't exceed the maximum dynamic range of the eg. integer signal values.
                dc_amplify	= 1 + abs( dc ) / max( abs( b ) for b in dfts )

            # Compute the resolution for the inverse DFT required to properly cover the binary
            # entropy.  However, limit size of the resultant DFT, as idft is O(N^2).  For a 512-bit
            # entropy split into 3-bit symbols, results in a N=170 DFT.  That's the 28,900
            # multiplications to produce an inverse-DFT.  That's the absolute largest we want to
            # deal with, and we don't want to produce anything bigger than an N=128 DFT, because we
            # don't need greater resolution than that to produce a smooth function graph in text.
            scale_signal	= 1
            scale_stride	= stride
            while scale_stride > 2 and len( dfts_rec ) * scale_signal * 2 <= 128:
                scale_stride   /= 2
                scale_signal   *= 2
            sigs		= signal_recover_real( dfts_rec, scale=scale_signal, integer=True, amplify=dc_amplify )

            pos			= ''
            neg			= ''
            o			= 0
            for i in range( symbols * stride ):
                o			= int( i / scale_stride )
                #print( f" - {i=:3} --> {o=:3} ==> {sigs[o]:7}" )
                pos	       += signal_draw( sigs[o], pos=True )
                neg	       += signal_draw( sigs[o], neg=True )
            harmonic_dBs	= [ f"{ordinal(h) if h else 'DC'} {into_dB(mags[h]/target):.1f}dB" for h in harmonic ]
            details	       += f"{offpref}{pos} {len(harmonic)} harmonics: {commas( harmonic_dBs, final_and=True )}\n"
            details	       += f"{offpref}{neg}  - "
            if 0 in harmonic:
                details	       += "DC offset"
            if 0 in harmonic and harmonic_freq:
                details	       += " and "
            if harmonic_freq:
                details	       += f"every {commas( harmonic_freq, final_and=True )} symbols"
            details	       += "\n"
            strongest		= Signal( dB=snr_dB, stride=stride, symbols=symbols, offset=offset, details=details )
    #mags_avgs			= [sum(col)/len(mags_all) for col in zip(*mags_all)]
    #print( f"avgs: {' '.join( f'{m:{stride*2}.1f}' for m in mags_avgs )}: {sum(mags_avgs):7.2f}" )
    return strongest
signal_entropy.signal_limits	= {  # noqa: E305
    False: {
        128: {
            3: {
                40: 3.8319094573028787,
                42: 3.685476090240114
            },
            4: {
                30: 3.8615459602092157,
                32: 3.7345780303889
            },
            5: {
                22: 4.031452452745891,
                24: 3.8701046211838714
            },
            6: {
                18: 4.064703542354124,
                20: 3.9093236736709005
            },
            7: {
                16: 3.9888900383171633,
                18: 3.782751595015048
            },
            8: {
                14: 4.0080294733416375,
                16: 3.8109570140209534
            }
        },
        160: {
            3: {
                50: 3.8379092760387756,
                52: 3.718158597189555
            },
            4: {
                38: 3.8755354830543545,
                40: 3.7335608496678003
            },
            5: {
                30: 3.871544429362041,
                32: 3.7384066763295962
            },
            6: {
                24: 3.958955796306026,
                26: 3.7860019541851724
            },
            7: {
                20: 3.9589683319930327,
                22: 3.7509059286588
            },
            8: {
                18: 4.003161116801384,
                20: 3.750478960622534
            }
        },
        192: {
            3: {
                62: 3.7990326479840117,
                64: 3.6734556303420725
            },
            4: {
                46: 3.815395598400365,
                48: 3.706303135801774
            },
            5: {
                36: 3.8676244259213672,
                38: 3.72179848809517
            },
            6: {
                30: 3.9077308083685156,
                32: 3.7827204635989755
            },
            7: {
                24: 3.9926484112501512,
                26: 3.9575120873481624
            },
            8: {
                22: 3.9392492333324904,
                24: 3.796701175618533
            }
        },
        224: {
            3: {
                72: 3.7782564719335396,
                74: 3.7040809282607565
            },
            4: {
                54: 3.8405424528165217,
                56: 3.738315589721119
            },
            5: {
                42: 3.862923384356215,
                44: 3.7435870871100922
            },
            6: {
                34: 3.9508243918812207,
                36: 3.8412655156588746
            },
            7: {
                30: 3.919800858328223,
                32: 3.744452833795885
            },
            8: {
                26: 3.928015382505577,
                28: 3.7267435566389167
            }
        },
        256: {
            3: {
                82: 3.806370027613541,
                84: 3.7619493887697253
            },
            4: {
                62: 3.82382599149047,
                64: 3.722971212374251
            },
            5: {
                48: 3.8777324591228752,
                50: 3.785035016049928
            },
            6: {
                40: 3.890868347621533,
                42: 3.7178010712693417
            },
            7: {
                34: 3.9103459886442242,
                36: 3.749124828108034
            },
            8: {
                30: 3.9381720284801585,
                32: 3.7641419877677595
            }
        },
        512: {
            3: {
                168: 3.8449196204941507,
                170: 3.7631094408144254
            },
            4: {
                126: 3.8423190039357342,
                128: 3.7808902262362367
            },
            5: {
                100: 3.8542627650321903,
                102: 3.773865897440794
            },
            6: {
                82: 3.861724791171357,
                84: 3.8341045873987407
            },
            7: {
                70: 3.864141100963424,
                72: 3.828268979559758
            },
            8: {
                62: 3.8294157442190024,
                64: 3.7911866343172504
            }
        }
    },
    True: {
        128: {
            3: {
                40: 4.059035156857346,
                42: 3.971692401025817
            },
            4: {
                30: 4.1483024026668245,
                32: 3.7402592967867974
            },
            5: {
                22: 4.423526762039983,
                24: 4.252455864761521
            },
            6: {
                18: 4.4658432794693415,
                20: 4.289839205249114
            },
            7: {
                16: 4.4553188372289965,
                18: 4.080751220352483
            },
            8: {
                14: 4.4394858537956905,
                16: 3.833429098349592
            }
        },
        160: {
            3: {
                50: 4.0418553868227205,
                52: 3.974100995247944
            },
            4: {
                38: 4.109990143437533,
                40: 3.6857894871960215
            },
            5: {
                30: 4.250347224202762,
                32: 3.7104125723998007
            },
            6: {
                24: 4.322116920166047,
                26: 4.210141749015608
            },
            7: {
                20: 4.457873575596333,
                22: 4.2962582680114325
            },
            8: {
                18: 4.457530992721327,
                20: 3.795257809455373
            }
        },
        192: {
            3: {
                62: 3.97667243358718,
                64: 3.6727653485324083
            },
            4: {
                46: 4.098491301720021,
                48: 3.712831538800005
            },
            5: {
                36: 4.21622370952482,
                38: 3.9745576377099625
            },
            6: {
                30: 4.24962628892952,
                32: 3.7307341765164725
            },
            7: {
                24: 4.45347505895079,
                26: 4.260646277940319
            },
            8: {
                22: 4.430469499308187,
                24: 3.73580831760822
            }
        },
        224: {
            3: {
                72: 4.011111103300378,
                74: 3.90746124565791
            },
            4: {
                54: 4.081269019267589,
                56: 3.7271617669568218
            },
            5: {
                42: 4.210201971324222,
                44: 4.065273612256523
            },
            6: {
                34: 4.29046478231144,
                36: 4.192458147743715
            },
            7: {
                30: 4.3031224754378385,
                32: 3.7645332019372657
            },
            8: {
                26: 4.3752737758292355,
                28: 3.7439793781541497
            }
        },
        256: {
            3: {
                82: 3.9867064854795853,
                84: 3.9474715330931964
            },
            4: {
                62: 4.091221861282323,
                64: 3.713189488198916
            },
            5: {
                48: 4.223821618652512,
                50: 4.112120735986639
            },
            6: {
                40: 4.286900236436957,
                42: 4.108363556032139
            },
            7: {
                34: 4.321051333229571,
                36: 4.120419486034919
            },
            8: {
                30: 4.3296525828892936,
                32: 3.7116192695666363
            }
        },
        512: {
            3: {
                168: 4.056315711850857,
                170: 3.9672213350986323
            },
            4: {
                126: 4.048192882854876,
                128: 3.7647648876385684
            },
            5: {
                100: 4.09557380634852,
                102: 3.9936613966057357
            },
            6: {
                82: 4.1778482028326875,
                84: 4.112025388076531
            },
            7: {
                70: 4.246425467555282,
                72: 4.176159483504127
            },
            8: {
                62: 4.2326162869241735,
                64: 3.702981814071318
            }
        }
    }
}


def shannon_entropy(
    entropy: bytes,
    stride: int			= 8,		# bits per symbol
    overlap: bool		= True,
    threshold: float		= None,         # Allow up to a certain % bits-per-symbol entropy deficit
    show_details: bool		= True,		# include signal details (incl. expensive ifft)
    snr_min: float		= 1/100,        # Minimum snr .01 == -40dB (eg. if all symbols unique)
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

    We provide some known defaults for evaluating data of various sizes, which are tested to produce
    only about a 1% rejection rate for good entropy.

    """
    entropy_hex			= codecs.encode( entropy, 'hex_codec' ).decode( 'ascii' )
    entropy_bin			= ''.join( f"{int(h,16):0>4b}" for h in entropy_hex )
    length			= len( entropy_bin )

    # Find all the unique n-bit symbols in the entropy at the desired offset(s)
    strongest			= None
    for offset in range( stride ) if overlap else (0,):
        # Calculate the frequency of each unique symbol
        frequency		= defaultdict( int )
        # How many full n-bit symbols fit in the entropy at the current symbol-start offset?
        symbols			= ( length - offset ) // stride
        for s in range( symbols ):
            i			= offset + s * stride
            symbol		= entropy_bin[i:i+stride]
            frequency[symbol]  += 1
        assert sum( frequency.values() ) == symbols, \
            f"Expected {symbols=} sum of probabilities events, found {frequency!r}"
        assert all( len( s ) == stride for s in frequency ), \
            f"Expected all {stride}-bit symbols, found {frequency!r}"

        bitspersymbol			= -sum(  # sum may range: (~-0.0,...)
            probability/symbols * math.log( probability/symbols, 2 )
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
        #     1/100 + 0    / ( .1 / ( 1 - 1/100 )) == 0.0100 == -10.0   dB  # -'ve below threshold
        #     1/100 + .043 / ( .1 / ( 1 - 1/100 )) == 0.4357 ==  -7.216 dB  #
        #     1/100 + .1   / ( .1 / ( 1 - 1/100 )) == 1.0000 ==   0.0   dB  # exactly at threshold
        #     1/100 + 1    / ( .1 / ( 1 - 1/100 )) == 9.9100 ==  19.20  dB  # +'ve above threshold
        #
        thresh			= shannon_entropy.shannon_limits.get(
            overlap, {} ).get(
                length, {} ).get(
                    stride ) if threshold is None else threshold
        assert thresh and 0 < thresh < 1, \
            f"A small +'ve ratio threshold of Shannon entropy deficit (0, 1] is required for {length}-bit entropy w/ {symbols} x {stride}-bit symbols eg. 10%, not {thresh!r}"

        snr			= snr_min + predictability / ( thresh / ( 1 - snr_min ))
        snr_dB			= into_dB( snr )
        weaker			= strongest and snr_dB < strongest.dB
        ( log.debug if snr_dB < 0 else log.info )(
            f"Found {len(frequency):3} unique (of {2**stride:5} possible) in {symbols:3}"
            f"x {stride:2}-bit symbols at offset {offset:2} in {length:4}-bit entropy:"
            f" Shannon Entropy {bitspersymbol:7.3f} b/s, P({shannon:7.3f}) unpredictable; {predictability=:7.3f}"
            f" vs. threshold={thresh:7.3f} == {snr=:7.3f} {snr_dB:7.3f}dB: {entropy_hex}"
        )
        if weaker:
            continue
        longest			= max(len(s) for s in frequency)
        details			= ''
        if snr_dB >= 0 and show_details:
            details	       += f"{len(frequency):2} unique"
            interesting		= sorted(
                frequency.items(), reverse=True, key=lambda kv: kv[1]
            )
            if stride < 7:
                details	       += f" (base-{2**stride})"
            details	       += ": " + commas(
                f"{v:>{longest}} = {int_decode( int( v, 2 ), stride=stride ).strip()}: {c:2}"
                for v,c in ( interesting[:4] if len( interesting ) > 5 else interesting )
            )
            if len( interesting ) > 5:
                details	       += f", ...x{len( interesting ) - 6}, " + commas(
                    f"{v:>{longest}} = {int_decode( int( v, 2 ), stride=stride ).strip()}: {c:2}"
                    for v,c in interesting[-2:]
                )
            details	       += "\n"
            # Show the frequency of the symbols
            offpref		= ''
            if offset > 8:
                details	       += f"...x{offset:<3}>{entropy_bin[offset:]}\n"
                offpref		= ' ' * 8
            else:
                details	       += f"{entropy_bin}\n"
                offpref		= ' ' * offset

            most		= interesting[0][1]
            least		= min( interesting[-1][1], most - 1 )
            scale		= 255 // ( most - least )
            wav			= ''
            for s in range( symbols ):
                i		= offset + s * stride
                symbol		= entropy_bin[i:i+stride]
                signal		= ( frequency[symbol] - least ) * scale - 128
                wav	       += stride * signal_draw( signal )
            details	       += f"{offpref}{wav}\n"

        strongest		= Signal(
            dB		= snr_dB,
            stride	= stride,
            symbols	= symbols,
            offset	= offset,
            details	= details,
        )
    return strongest
shannon_entropy.shannon_limits	= {  # noqa: E305
    False: {
        128: {
            3: 0.14019101211428098,
            4: 0.2171524340774941,
            5: 0.30713834645661736,
            6: 0.1816854359968526,
            7: 0.13342390650130254,
            8: 0.10552310877642387
        },
        160: {
            3: 0.11057723763050892,
            4: 0.1744843783599689,
            5: 0.28299092891476074,
            6: 0.1761722851760338,
            7: 0.12975999942499564,
            8: 0.09928308012524291
        },
        192: {
            3: 0.09253435025671844,
            4: 0.1456160815841306,
            5: 0.23107460801496676,
            6: 0.1786869224456945,
            7: 0.12135312641853993,
            8: 0.09236474782597097
        },
        224: {
            3: 0.08437544813234008,
            4: 0.12344441710449479,
            5: 0.20023712270178562,
            6: 0.17586978273318993,
            7: 0.12103055216465301,
            8: 0.08885130467252834
        },
        256: {
            3: 0.07899726657064883,
            4: 0.10986451280885183,
            5: 0.17685089046815017,
            6: 0.18089586818651493,
            7: 0.12034741739974093,
            8: 0.0868358375224554
        },
        512: {
            3: 0.07790480669136064,
            4: 0.07790480669136064,
            5: 0.09071156437595747,
            6: 0.1528917619447544,
            7: 0.13006695660607703,
            8: 0.08296364156731802
        }
    },
    True: {
        128: {
            3: 0.15550747522807437,
            4: 0.24661163176093312,
            5: 0.3523433565963667,
            6: 0.21534352560263997,
            7: 0.16411100479228236,
            8: 0.136414702002971
        },
        160: {
            3: 0.12235932220703663,
            4: 0.1939517479905352,
            5: 0.443059638567671,
            6: 0.20036194013482425,
            7: 0.15050146936554146,
            8: 0.11908287323944898
        },
        192: {
            3: 0.1009472582720825,
            4: 0.16258867795098023,
            5: 0.34646648683625064,
            6: 0.19299661700728024,
            7: 0.1427661144625154,
            8: 0.10704829451650133
        },
        224: {
            3: 0.08865058569899047,
            4: 0.13975704077911924,
            5: 0.2641791211100633,
            6: 0.1943829468972367,
            7: 0.13955446956607254,
            8: 0.10244365652109154
        },
        256: {
            3: 0.08168351670153086,
            4: 0.12141626752694244,
            5: 0.1967404982010119,
            6: 0.2397004855223926,
            7: 0.13609286793923406,
            8: 0.09979325030179034
        },
        512: {
            3: 0.07790480669136064,
            4: 0.07790480669136064,
            5: 0.09869307232869345,
            6: 0.1826087090056934,
            7: 0.13963588440239252,
            8: 0.09058107616905901
        }
    }
}


def scan_entropy(
    entropy: bytes,
    strides: Optional[Union[int,Tuple[int,int]]] = None,  # If only a specific stride/s makes sense, eg. for ASCII symbols
    overlap: bool		= True,
    ignore_dc: bool		= False,
    show_details: bool		= True,
    signal_threshold: Optional[float]	= None,
    shannon_threshold: Optional[float]	= None,
) -> Tuple[List[Signal],List[Signal]]:
    """Defaults to as many symbols as we can manage, given 'overlap' (which ensures we scan scan at
    least a full stride of bit offsets).

    There is usually little benefit to performing both with/without overlap; we still analyze the
    0-offset symbols, but perhaps with a couple fewer total symbols, and with a slightly higher
    threshold.

    """
    if strides is None:
        strides			= (3, 9)
    else:
        try:
            _,_			= strides
        except TypeError:
            strides		= (int(strides), int(strides)+1)

    signals			= sorted(
        (
            s
            for s in (
                signal_entropy( entropy, stride=stride, overlap=overlap, ignore_dc=ignore_dc,
                                show_details=show_details, threshold=signal_threshold )
                for stride in range( *strides )
            )
            if s.dB >= 0
        ), reverse=True )
    shannons			= sorted(
        (
            s
            for s in (
                shannon_entropy( entropy, stride=stride, overlap=overlap,
                                 show_details=show_details, threshold=shannon_threshold )
                for stride in range( *strides )
            )
            if s.dB >= 0
        ), reverse=True )
    return signals, shannons


def display_entropy( signals, shannons, what=None ):
    result			= None
    if signals or shannons:
        report			= ''
        dBs			= sorted( list( s.dB for s in signals ) + list( s.dB for s in shannons) )
        dBr			= dBs[:1] + dBs[max( 1, len(dBs)-1):]
        report		       += f"Entropy analysis {('of ' + what) if what else ''}: {len(signals)+len(shannons)}x"
        report		       += f" {'-'.join( f'{dB:.1f}' for dB in dBr )}dB non-random energy patterns in"
        report		       += f" {commas( sorted( set( s.stride for s in signals )), final_and=True)}-bit symbols\n"
        for s,summary in sorted(
                [
                    (s, f"{s.dB:5.1f}dB Signal harmonic feature at offset {s.offset} in {s.symbols}x {s.stride}-bit symbols")
                    for s in signals
                ] + [
                    (s, f"{s.dB:5.1f}dB Shannon entropy reduced at offset {s.offset} in {s.symbols}x {s.stride}-bit symbols")
                    for s in shannons
                ], reverse=True ):
            report	       += f"-{summary}{': ' if s.details else ''}\n"
            if s.details:
                report	       += f"{s.details}\n"
        result			= report
    return result


def analyze_entropy(
    entropy: bytes,
    strides: Optional[Union[int,Tuple[int,int]]] = None,  # If only a specific stride/s makes sense, eg. for ASCII symbols
    overlap: bool		= True,
    ignore_dc: bool		= False,
    what: Optional[str]		= None,
    show_details: bool		= True,
    signal_threshold: Optional[float]	= None,
    shannon_threshold: Optional[float]	= None,
) -> Optional[str]:
    """Analyzes the provided entropy.  If patterns are found, reports the findings; the peak Signal
    and the aggregate report: (Signal, "...").

    Seek strong Signals or weak Shannon Entropy, across a number of different interpretations (bit
    strides and overlaps) of the entropy data.  We do not know where poor entropy may hide...

    Since the probability of a signal being found is:

        P( A or B or ... or Z ) = P(A) + P(B) + ... + P(Z) - P(A and B and ... Z )
      = P( A or B or ... or Z ) = P(A) + P(B) + ... + P(Z) - ( P(A) * P(B) * ... P(Z) )

    since we set the {signal,shannon}_entropy threshold values at ~ <1%, we know the P(A and B...)
    term is very small; the probability we'll find an entropy failure it basically is the sum of the
    individual probabilities of each test failing.

    So, if we try 6 of each analysis, that's 12 * 1% =~= 12%.  If we want a total failure of about
    1%, so we must target a ~0.1% failure on good entropy for each test.

    However, it seems likely that if a signal appears in one bit-stride, it may appear in others, so
    perhaps the analysis on different strides may be related.  So, it might be practical to target
    0.25% failure on each individual test.

    """
    return display_entropy(
        *scan_entropy(
            entropy, strides, overlap, ignore_dc=ignore_dc, show_details=show_details,
            signal_threshold=signal_threshold, shannon_threshold=shannon_threshold ),
        what=what
    )
