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
        #print( f"dnoi: {' '.join( f'{c:{stride}.1f}({mags[i] / target if target else 0:{stride-2}.1f})' for i,c in enumerate( curs ))}: {target=:7.1f}" )

    # Return the noise threshold target magnitude deduced, and the index,SNR for each signal bin,
    # sorted by SNR
    return target, sorted(
        ( (i, mags[i] / target if target else 0) for i in snrs ),
        key	= lambda e: e[1],
        reverse	= True,
    )


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
) -> Optional[Signal]:
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
    the unlikely "perfect" noise-free signal (or signals w/ *only* a DC component if we ignore_dc.)

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
                peak		= max( abs( b ) for b in dfts )
                if peak:
                    dc_amplify	= 1 + abs( dc ) / peak

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
            harmonic_dBs	= [ f"{ordinal(h) if h else 'DC'} {into_dB(mags[h]/target) if target else 0.0:.1f}dB" for h in harmonic ]
            details	       += f"{offpref}{pos} {len(harmonic)} harmonics: {commas( harmonic_dBs, final='and' )}\n"
            details	       += f"{offpref}{neg}  - "
            if 0 in harmonic:
                details	       += "DC offset"
            if 0 in harmonic and harmonic_freq:
                details	       += " and "
            if harmonic_freq:
                details	       += f"every {commas( harmonic_freq, final='and' )} symbols"
            details	       += "\n"
            strongest		= Signal( dB=snr_dB, stride=stride, symbols=symbols, offset=offset, details=details )
    #mags_avgs			= [sum(col)/len(mags_all) for col in zip(*mags_all)]
    #print( f"avgs: {' '.join( f'{m:{stride*2}.1f}' for m in mags_avgs )}: {sum(mags_avgs):7.2f}" )
    return strongest

signal_entropy.signal_limits	= {  # noqa: E305
    False: {
        128: {
            3: {
                40: 3.7959290562900327,
                42: 3.647561915551939
            },
            4: {
                30: 3.8431997942042178,
                32: 3.8749244192110694
            },
            5: {
                22: 4.01132938746108,
                24: 3.855818706529049
            },
            6: {
                18: 3.9821710568269393,
                20: 4.10175893691386
            },
            7: {
                16: 3.9998153373627243,
                18: 3.86288147813215
            },
            8: {
                14: 4.035389231470121,
                16: 3.85295803340856
            }
        },
        160: {
            3: {
                50: 3.768307059766632,
                52: 3.657642158466681
            },
            4: {
                38: 3.927175392223398,
                40: 3.644644794089787
            },
            5: {
                30: 4.004859915596088,
                32: 3.723428336867249
            },
            6: {
                24: 3.921311891749215,
                26: 3.7484305351772997
            },
            7: {
                20: 4.053741462343345,
                22: 3.7022202971931337
            },
            8: {
                18: 3.902181587171419,
                20: 3.682978660449477
            }
        },
        192: {
            3: {
                62: 3.78844766566635,
                64: 3.6289494114027234
            },
            4: {
                46: 3.9167065596553523,
                48: 3.6393513794634913
            },
            5: {
                36: 3.8915275898547788,
                38: 3.7473928123694793
            },
            6: {
                30: 3.9132919286186874,
                32: 3.904575332226886
            },
            7: {
                24: 4.18637617875428,
                26: 3.8093336871612897
            },
            8: {
                22: 4.046780450578674,
                24: 3.766307067356347
            }
        },
        224: {
            3: {
                72: 3.6989229751871116,
                74: 3.858442530730556
            },
            4: {
                54: 3.868023231802504,
                56: 3.821289665038688
            },
            5: {
                42: 3.9244827423261506,
                44: 3.7255928738074235
            },
            6: {
                34: 3.9796568789267033,
                36: 3.8424176850637064
            },
            7: {
                30: 3.884348278904745,
                32: 3.7274499501787015
            },
            8: {
                26: 3.9286076413465723,
                28: 3.8212509511408332
            }
        },
        256: {
            3: {
                82: 3.874105542934525,
                84: 3.8031640175138075
            },
            4: {
                62: 3.8535667393555895,
                64: 3.6702455043197517
            },
            5: {
                48: 3.966192695309544,
                50: 3.810215205319617
            },
            6: {
                40: 3.780615203182523,
                42: 3.7166374907758537
            },
            7: {
                34: 3.7632487952840674,
                36: 3.820508681003472
            },
            8: {
                30: 3.851962569866387,
                32: 3.79387401596316
            }
        },
        512: {
            3: {
                168: 3.8510228062858536,
                170: 3.6930501052854368
            },
            4: {
                126: 3.8739687818152095,
                128: 3.8390294681049797
            },
            5: {
                100: 3.8944436960232816,
                102: 3.8213977750827777
            },
            6: {
                82: 3.8651467331943445,
                84: 4.00628842914143
            },
            7: {
                70: 3.8977031690387087,
                72: 3.7538315552341635
            },
            8: {
                62: 3.956950350574148,
                64: 3.7809092998228437
            }
        }
    },
    True: {
        128: {
            3: {
                40: 4.015412815647333,
                42: 4.049142728796211
            },
            4: {
                30: 4.084354511564386,
                32: 3.651281177941025
            },
            5: {
                22: 4.190848444589507,
                24: 4.358983589533379
            },
            6: {
                18: 4.433227305912341,
                20: 4.300266280446989
            },
            7: {
                16: 4.63348257265716,
                18: 4.251514929567565
            },
            8: {
                14: 4.539487223257121,
                16: 3.8298375269653464
            }
        },
        160: {
            3: {
                50: 4.102991330499331,
                52: 3.9201904890263806
            },
            4: {
                38: 3.9660043286866316,
                40: 3.8885457864057296
            },
            5: {
                30: 4.1534554695112424,
                32: 3.875257196943185
            },
            6: {
                24: 4.314705804221271,
                26: 4.276913496937379
            },
            7: {
                20: 4.484017655351361,
                22: 4.1891981747029154
            },
            8: {
                18: 4.403790052686062,
                20: 3.8171358828247257
            }
        },
        192: {
            3: {
                62: 3.946957410520236,
                64: 3.707417210141612
            },
            4: {
                46: 4.243992805910835,
                48: 3.5294430695860983
            },
            5: {
                36: 4.307388423581146,
                38: 3.8978305998977363
            },
            6: {
                30: 4.296222571278912,
                32: 3.666087989048472
            },
            7: {
                24: 4.483230938800909,
                26: 4.2688078347472285
            },
            8: {
                22: 4.3975014624329,
                24: 3.9299336762739103
            }
        },
        224: {
            3: {
                72: 4.020867167290543,
                74: 4.115472579780688
            },
            4: {
                54: 4.155505881349097,
                56: 3.611932501064818
            },
            5: {
                42: 4.296142369450004,
                44: 4.075549039418728
            },
            6: {
                34: 4.339759784005132,
                36: 4.199962133110188
            },
            7: {
                30: 4.323936203605842,
                32: 4.029221841050185
            },
            8: {
                26: 4.470823290289282,
                28: 3.8214418599675444
            }
        },
        256: {
            3: {
                82: 3.9159493966982546,
                84: 3.9052586437888848
            },
            4: {
                62: 4.095016786713433,
                64: 3.6867364579681587
            },
            5: {
                48: 4.260740010786478,
                50: 4.152970392617726
            },
            6: {
                40: 4.298675707470258,
                42: 3.9884678302777594
            },
            7: {
                34: 4.218469498120002,
                36: 4.09636224540939
            },
            8: {
                30: 4.299777044591192,
                32: 3.633717478015482
            }
        },
        512: {
            3: {
                168: 4.016185108804742,
                170: 4.028203232067135
            },
            4: {
                126: 4.039199984086117,
                128: 3.694796108995797
            },
            5: {
                100: 4.012546598293882,
                102: 3.8791966508371343
            },
            6: {
                82: 4.071645334320387,
                84: 4.31042853254462
            },
            7: {
                70: 4.1408664186751505,
                72: 4.060968141932326
            },
            8: {
                62: 4.290524429312738,
                64: 3.8260046870654842
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
    N: Optional[int]		= None,		# If a max. number of unique symbols is known eg. dice
) -> Optional[Signal]:
    """Estimates the "Symbolised Shannon Entropy" for stride-bit chunks of the provided entropy; by
    default, since we don't know the bit offset of any pattern, we'll scan at each possible bit
    offset (overlap = True).

    We'll compute the estimated predictability of the entropy, in the range [0,1], where 0 is
    unpredictable (high entropy), and 1 is totally predictable (no entropy), but as a dB range,
    where -'ve dB is below the threshold and acceptable, and +'ve is above the predictability
    threshold, and is unacceptable.

    Typically, for large entropy and/or small 'stride' values, the number of unique values N found
    should tend toward 2^stride.  However, for small entropy (eg. insufficient data) or small known
    N (eg. die rolls), we expect to see less unique values than would be implied by the stride.
    Therefore, we reduce the N in those cases.

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
        N_min			= min( N or symbols, symbols, 2**stride )
        assert len( frequency ) <= N_min, \
            f"Observed {len(frequency)} unique symbols; more than expected by min({N=}, {symbols=} or {2**stride=})"
        if N_min > 1:
            shannon		= bitspersymbol / math.log( N_min, 2 )

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
        assert thresh and 0 < thresh <= 2, \
            f"A small +'ve ratio threshold of Shannon entropy deficit ~ (0, 1] is required for {length}-bit entropy w/ {symbols} x {stride}-bit symbols eg. 10%, not {thresh!r}"

        snr			= snr_min + predictability / ( thresh / ( 1 - snr_min ))
        snr_dB			= into_dB( snr )
        weaker			= strongest and snr_dB < strongest.dB
        ( log.debug if snr_dB < 0 else log.info )(
            f"Found {len(frequency):3} unique (of {N_min:3} possible) in {symbols:3}"
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
            3: 0.13774543485038598,
            4: 0.21352083735742364,
            5: 0.25857335693364575,
            6: 0.18024155906953593,
            7: 0.13393449488438314,
            8: 0.10565473026867159
        },
        160: {
            3: 0.10849932592752157,
            4: 0.1732988370721074,
            5: 0.2539763216172974,
            6: 0.17643151270139718,
            7: 0.13155406158983765,
            8: 0.09785468929753503
        },
        192: {
            3: 0.09151054889558748,
            4: 0.14093100938467484,
            5: 0.2264278561929118,
            6: 0.1760839014542283,
            7: 0.1271444744051939,
            8: 0.08862800898521093
        },
        224: {
            3: 0.07916495360459236,
            4: 0.12252481621910122,
            5: 0.20074807382273818,
            6: 0.18204659485920255,
            7: 0.12255892501570535,
            8: 0.08642238826221553
        },
        256: {
            3: 0.06465367140204993,
            4: 0.11144594962520256,
            5: 0.178731925009808,
            6: 0.1819179694876547,
            7: 0.12157462190503683,
            8: 0.0860841002032892
        },
        512: {
            3: 0.03404772973774162,
            4: 0.05292514037032153,
            5: 0.09170667883453174,
            6: 0.15075753744881315,
            7: 0.1264033310600746,
            8: 0.08353573387816829
        }
    },
    True: {
        128: {
            3: 0.15298580418729513,
            4: 0.2451904173880027,
            5: 0.2830395399608447,
            6: 0.2028328095184408,
            7: 0.16471175054429602,
            8: 0.13936432438214608
        },
        160: {
            3: 0.12038637754457157,
            4: 0.19979446717148586,
            5: 0.28247744681759446,
            6: 0.19821636321414943,
            7: 0.15105344745335572,
            8: 0.1174014993567044
        },
        192: {
            3: 0.09947716314352242,
            4: 0.16262594321420024,
            5: 0.24061446698597114,
            6: 0.1988991682768491,
            7: 0.14865256303627913,
            8: 0.11409493984939509
        },
        224: {
            3: 0.09107077508129978,
            4: 0.13949972486012852,
            5: 0.21449493978928671,
            6: 0.18980489337861572,
            7: 0.14016478187097317,
            8: 0.10760893832461406
        },
        256: {
            3: 0.07641224240206347,
            4: 0.11638307614673703,
            5: 0.19375895117831868,
            6: 0.19231952709666766,
            7: 0.13550085464769412,
            8: 0.09588448833768029
        },
        512: {
            3: 0.038422756462380414,
            4: 0.057658537793532146,
            5: 0.09918546794102677,
            6: 0.16114705850045197,
            7: 0.1402080308731611,
            8: 0.09257360822755922
        }
    }
}


def scan_entropy(
    entropy: bytes,
    strides: Optional[Union[int,Tuple[int,int]]] = None,  # If only a specific stride/s makes sense, eg. for ASCII symbols
    overlap: bool		= True,
    ignore_dc: bool		= False,
    show_details: bool		= True,
    N: Optional[int]		= None,			# shannon_entropy may specify limited unique symbols
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
                shannon_entropy( entropy, stride=stride, overlap=overlap, N=N,
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
        report		       += f" {'-'.join( f'{dB:.1f}' for dB in dBr )}dB non-random patterns in"
        report		       += f" {commas( sorted( set( s.stride for s in signals )), final='and' )}-bit symbols\n\n"
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
    N: Optional[int]		= None,			# shannon_entropy may specify limited unique symbols
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
            entropy, strides, overlap, ignore_dc=ignore_dc, show_details=show_details, N=N,
            signal_threshold=signal_threshold, shannon_threshold=shannon_threshold ),
        what=what
    )
