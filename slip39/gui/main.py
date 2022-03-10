import argparse
import codecs
import hashlib
import logging
import math
import os
import re
import sys
import subprocess

from itertools import islice

import PySimpleGUI as sg

from ..api		import Account, create, group_parser, random_secret, cryptopaths_parser, paper_wallet_available
from ..recovery		import recover, recover_bip39
from ..util		import log_level, log_cfg, ordinal, chunker
from ..layout		import write_pdfs, printers_available
from ..defaults		import (
    GROUPS, GROUP_THRESHOLD_RATIO, MNEM_PREFIX, CRYPTO_PATHS, BITS,
    CARD_SIZES, CARD, PAPER_FORMATS, PAPER, WALLET_SIZES, WALLET,
    MNEM_CONT, LAYOUT, LAYOUT_OPTIONS,
)

log				= logging.getLogger( __package__ )


font_points			= 14
font				= ('Courier', font_points+0)
font_dense			= ('Courier', font_points-2)
font_small			= ('Courier', font_points-4)
font_bold			= ('Courier', font_points+2, 'bold italic')

I_kwds				= dict(
    change_submits	= True,
    font		= font,
)
I_kwds_small			= dict(
    change_submits	= True,
    font		= font_small,
)
T_kwds				= dict(
    font		= font,
)
T_kwds_dense			= dict(
    font		= font_dense,
)
F_kwds				= dict(
    font		= font,
)
B_kwds				= dict(
    font		= font,
    enable_events	= True,
)

prefix				= (15, 1)
inputs				= (40, 1)
inlong				= (128,1)       # 512-bit seeds require 128 hex nibbles
shorty				= (10, 1)
tiny				= ( 3, 1)
mnemos				= (192,3)


def groups_layout(
    names,
    group_threshold,
    groups,
    passphrase		= None,
    cryptocurrency	= None,
    wallet_pwd		= None,			# If False, disable capability
    wallet_pwd_hint	= None,
    wallet_derive	= None,
    controls		= None,			# Default is simplest controls LAYOUT_OPTIONS[0];
    printers		= None,			# Any printers available at the present time
):
    """Return a layout for the specified number of SLIP-39 groups.

    """

    group_body			= [
        sg.Frame( '#', [
            [
                sg.Column( [
                    [
                        sg.Text( f'{g+1}',                                                      **T_kwds ),
                    ]
                    for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
                ],                                      key='-GROUP-NUMBER-' )
            ]
        ],                                                                                      **F_kwds ),
        sg.Frame( 'Group Name; To recover, collect at least...', [
            [
                sg.Column( [
                    [
                        sg.Input( f'{g_name}',          key=f'-G-NAME-{g}',                     **I_kwds ),
                    ]
                    for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
                ],                                      key='-GROUP-NAMES-' )
            ]
        ],                                                                                      **F_kwds ),
        sg.Frame( '#', [
            [
                sg.Column( [
                    [
                        sg.Input( f'{g_need}',          key=f'-G-NEED-{g}',     size=tiny,     **I_kwds )
                    ]
                    for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
                ],                                      key='-GROUP-NEEDS-' )
            ]
        ],                                                                                     **F_kwds ),
        sg.Frame( 'of #', [
            [
                sg.Column( [
                    [
                        sg.Input( f'{g_size}',          key=f'-G-SIZE-{g}',     size=tiny,     **I_kwds )
                    ]
                    for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
                ],                                      key='-GROUP-SIZES-' )
            ]
        ],                                                                                     **F_kwds ),
    ]

    if wallet_pwd is False:
        log.warning( "Disabling Paper Wallets capability: API unavailable" )

    LO				= LAYOUT_OPTIONS[controls] if controls is not None else LAYOUT
    LO_REC			= LO != LAYOUT_OPTIONS[0]		# True iff LO == Recover or Pro
    LO_PRO			= LO == LAYOUT_OPTIONS[-1]		# True iff LO == Pro

    CRYPTO_DISPLAY		= list(
        symbol
        for symbol in Account.CRYPTO_NAMES.values()  # Retains desired ordering (vs. CRYPTOCURRENCIES set)
        if LO_PRO or symbol not in Account.CRYPTOCURRENCIES_BETA
    )

    layout                      = [
        [
            sg.Frame( '1. Name(s) and formats of SLIP-39 Cards for output PDF File(s)', [
                [
                    sg.Column( [
                        [
                            sg.Text( f"Seed Name{LO_PRO and '(s, ...)' or ''}:",size=prefix,    **T_kwds ),
                            sg.Input( f"{', '.join(names)}",key='-NAMES-',      size=inputs,    **I_kwds ),
                        ],
                        [
                            sg.Text( "SLIP-39 Card size:",                                      **T_kwds ),
                        ] + [
                            sg.Radio( f"{cs}",     "CS", key=f"-CS-{cs}-",      default=(cs == CARD), **B_kwds )
                            for ci,cs in enumerate( CARD_SIZES )
                            if controls or ci < len( CARD_SIZES ) // 2
                        ]
                    ] ),
                    sg.Column( [
                        [
                            sg.Text( "Controls:",                                                **T_kwds ),
                        ] + [
                            sg.Radio( f"{lo:6}",  "LO", key=f"-LO-{li}-",       default=(lo == LO), **B_kwds )
                            for li,lo in enumerate( LAYOUT_OPTIONS )
                        ],
                        [
                            sg.Text( "on Paper:",                                                 **T_kwds ),
                        ] + [
                            sg.Radio( f"{pf:6}",  "PF", key=f"-PF-{pf}-",       default=(pf == PAPER),**B_kwds )
                            for pi,pf in enumerate( PAPER_FORMATS )
                            if controls or pi < len( PAPER_FORMATS ) // 2
                        ],
                    ] )
                ]
            ],                                          key='-OUTPUT-F-',                       **F_kwds ),
        ],
    ] + [
        [
            # SLIP-39 only available in Recovery; SLIP-39 Passphrase only in Pro; BIP-39 and Fixed Hex only in Pro
            sg.Frame( '2. Seed Data Source (128-bit is fine; 256-bit produces many Mnemonic words to type into your Trezor; 512-bit aren\'t Trezor compatible)', [
                [
                    sg.Text( "Random:",                                                         **T_kwds ),
                    sg.Radio( "128-bit",          "SD", key='-SD-128-RND-',     default=True,   **B_kwds ),
                    sg.Radio( "256-bit",          "SD", key='-SD-256-RND-',     default=False,  **B_kwds ),
                    sg.Radio( "512-bit",          "SD", key='-SD-512-RND-',     default=False,  **B_kwds ),
                    sg.Text( "Recover:",                                        visible=LO_REC, **T_kwds ),
                    sg.Radio( "SLIP-39",          "SD", key='-SD-SLIP-',        visible=LO_REC, **B_kwds ),
                    sg.Radio( "512-bit BIP-39",   "SD", key='-SD-BIP-',         visible=LO_PRO, **B_kwds ),
                    sg.Checkbox( 'SLIP-39 Passphrase (NOT Trezor compatible)',
                                                        key='-SD-PASS-C-',      visible=LO_PRO,  **B_kwds ),
                ],
                [
                    sg.Text("Fixed: ",                                          visible=LO_PRO, **T_kwds ),
                ] + [
                    sg.Radio( f"{b}-bit",  "SD", key=f"-SD-{b}-FIX-",           visible=LO_PRO, **B_kwds )
                    for b in BITS
                ] + [
                    sg.Frame( 'Only use if a Passphrase was provided when the Mnemonic was created)', [
                        [
                            sg.Text( "Passphrase (decrypt): ",                  size=prefix,    **T_kwds ),
                            sg.Input( "",               key='-SD-PASS-',        size=inputs,    **I_kwds ),
                        ],
                    ],                                  key='-SD-PASS-F-',      visible=False,  **F_kwds ),
                ],
                [
                    sg.Frame( 'From Mnemonic(s):', [
                        [
                            #sg.Text( "Mnemonic(s): ",   key='-SD-DATA-T-',      size=prefix,    **T_kwds ),
                            sg.Multiline( "",           key='-SD-DATA-',        size=mnemos,    **I_kwds_small ),
                        ],
                    ],                                  key='-SD-DATA-F-',      visible=False,  **F_kwds ),
                ],
                [
                    sg.Text( "Seed Data: ",                                     visible=LO_REC,
                                                                                size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SD-SEED-',        visible=LO_REC,
                                                                                size=inlong,    **T_kwds ),
                ],
            ],                                          key='-SD-SEED-F-',                      **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( '3. Extra Seed Entropy (XOR-ed; Recommended if you don\'t trust our randomness ;-), or specify multiple Seeds', [
                [
                    sg.Radio( "None",             "SE", key='-SE-NON-',         visible=LO_REC, default=True,   **B_kwds ),
                    sg.Radio( "Dice rolls, ...",  "SE", key='-SE-SHA-',         visible=LO_REC, **B_kwds ),
                    sg.Radio( "Hex",              "SE", key='-SE-HEX-',         visible=LO_PRO, **B_kwds ),
                ],
                [
                    sg.Frame( 'Entropy', [
                        [
                            sg.Text( "Hex digits: ",    key='-SE-DATA-T-',      size=prefix,    **T_kwds ),
                            sg.Input( "",               key='-SE-DATA-',        size=inlong,    **I_kwds ),
                        ],
                    ],                                  key='-SE-DATA-F-',      visible=False,  **F_kwds ),
                ],
                [
                    sg.Text( "Seed Entropy: ",                                  visible=LO_REC,size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SE-SEED-',        visible=LO_REC,size=inlong,    **T_kwds ),
                ],
            ],                                          key='-SE-SEED-F-',                      **F_kwds ),
        ]
    ] + [
        [
            sg.Frame( '4. Master Secret Seed & SLIP-39 Recovery Groups; Up to 16 groups w/ 1-16 cards required.', [
                [
                    sg.Text( "Seed: ",                                          size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SEED-',           size=inlong,    **T_kwds ),
                ],
                [
                    sg.Column( [
                        [
                            sg.Text( "Recovery needs: ",                        size=prefix,    **T_kwds ),
                            sg.Input( f"{group_threshold}", key='-THRESHOLD-',  size=tiny,      **I_kwds ),
                            sg.Text( f"of {len(groups)}", key='-RECOVERY-',                     **T_kwds ),
                            sg.Button( '+', **B_kwds ),
                            sg.Text( "Mnemonic Groups",                                **T_kwds ),
                            sg.Checkbox( 'SLIP-39 Passphrase',
                                                        key='-PASSPHRASE-C-',   visible=LO_PRO, **B_kwds ),
                        ],
                        [
                            sg.Frame( 'NOT Trezor compatible; perhaps use \"Hidden wallet\" on device instead?', [
                                [
                                    sg.Text( "Passphrase (encrypt): ",                          **T_kwds ),
                                    sg.Input( f"{passphrase or ''}",
                                                        key='-PASSPHRASE-',     size=inputs,    **I_kwds ),
                                ],
                            ],                          key='-PASSPHRASE-F-',   visible=False,  **F_kwds ),
                        ],
                        group_body,
                    ] ),
                    sg.Multiline( "",           key='-INSTRUCTIONS-',   size=(80,12),          **T_kwds_dense ),
                ],
            ],                                          key='-GROUPS-F-',                       **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( '5. Cryptocurrencies and Paper Wallets (for importing into software wallets; not needed if entering SLIP-39 Mnemonics into Trezor)', [
                [
                    sg.Column( [
                        [
                            sg.Checkbox( f"{c}", default=c in ( cryptocurrency or CRYPTO_PATHS ),
                                                        key=f"-CRYPTO-{c}-",                    **B_kwds )
                            for c in c_row
                        ]
                        for c_row in chunker(
                            CRYPTO_DISPLAY, int( round( math.sqrt( len( CRYPTO_DISPLAY )) + .25 ))
                        )
                    ],                                                          visible=LO_REC )
                ] + [
                    sg.Frame( 'Paper Wallet Password/Hint (empty, if no Paper Wallets desired)', [
                        [
                            sg.Input( default_text=wallet_pwd or '',
                                                        key='-WALLET-PASS-',    size=inputs,    **I_kwds ),
                            sg.Text( "Hint: ",                                                  **T_kwds ),
                            sg.Input( default_text=wallet_pwd_hint or '',
                                                        key='-WALLET-HINT-',    size=shorty,    **I_kwds ),
                        ],
                    ],                                                          visible=LO_REC, **F_kwds ),
                    sg.Frame( '# to Derive:', [
                        [
                            sg.Input( default_text=wallet_derive or '1',
                                                        key='-WALLET-DERIVE-',  size=shorty,    **I_kwds ),
                        ],
                    ],                                                          visible=LO_REC, **F_kwds ),
                ] + [
                    sg.Column( [
                        [
                            sg.Text( 'Paper wallets / page:',                                   **T_kwds )
                        ],
                        [
                            sg.Radio( f"{ws}", "WS",    default=ws == WALLET,
                                                        key=f"-WALLET-SIZE-{ws}-",              **B_kwds )
                            for ws in WALLET_SIZES
                        ],
                    ],                                                          visible=LO_REC )
                ],
            ],                                          key='-WALLET-F-',       visible=wallet_pwd is not False,
                                                                                                **F_kwds ),  # noqa: E126
        ],
    ] + [
        [
            sg.Frame( '6. Summary of your SLIP-39 Recovery Groups.  When this looks good, hit Save (to removable USB)!', [
                [
                    sg.Input( sg.user_settings_get_entry( "-target folder-", ""),
                                                        key='-SAVE-',           visible=False,  **I_kwds ),
                    sg.FolderBrowse( 'Save',            target='-SAVE-',                        **B_kwds ),
                    sg.Button( 'Print',                 key='-PRINT-',         visible=printers is not None,
                                                                                                **B_kwds ),
                    sg.Combo( printers or [],           key='-PRINTER-',       visible=printers is not None,
                              # default_value=printers[0] if printers else None,  # Leave empty, to allow selecting (default) printer
                                                                                                **B_kwds ),
                    sg.Text(                            key='-SUMMARY-',                        **T_kwds ),
                ]
            ],                                          key='-SUMMARY-F-',                      **F_kwds ),
        ],
        [
            sg.Frame( '7. Status. Some Crypto Wallet addesses derived from your Seed, or any problems we detect.', [
                [
                    sg.Text(                            key='-STATUS-',                         **T_kwds ),
                ]
            ],                                          key='-STATUS-F-',                       **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( '8. SLIP-39 Recovery Mnemonics produced.  These will be saved to the PDF on cards.', [
                [
                    sg.Multiline( "",                   key='-MNEMONICS-'+sg.WRITE_ONLY_KEY,
                                                                                size=mnemos,    **I_kwds_small )
                ]
            ],                                          key='-MNEMONICS-F-',    visible=LO_PRO, **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( '9. Seed Recovered from SLIP-39 Mnemonics, proving that we can actually use the Mnemonics to recover the Seed', [
                [
                    sg.Text( "Seed Verified: ",                                 size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SEED-RECOVERED-', size=inlong,    **T_kwds ),
                ],
            ],                                          key='-RECOVERED-F-',    visible=LO_PRO, **F_kwds ),
        ],
    ]
    return layout


def mnemonic_continuation( lines ):
    """Filter out any prefixes consisting of word/space symbols followed by a single non-word/space
    symbol, before any number of Mnemonic word/space symbols:

                    Group  1 { word word ...
                    Group  2 ╭ word word ...
                             ╰ word word ...
                    Group  3 ┌ word word ...
                             ├ word word ...
                             └ word word ...
                    ^^^^^^^^ ^ ^^^^^^^^^^...
                           | | |
           word/digit/space* | word/space*
                             |
                  single non-word/digit/space

    Any joining lines w/ a recognized MNEM_CONT prefix symbol (a UTF-8 square/curly bracket top or
    center segment) are concatenated.  Any other non-prefixed or unrecognized word/space symbols are
    considered complete mnemonic lines.

    """
    mnemonic			= []
    for li in lines:
        m			= re.match( r"([\w\d\s]*[^\w\d\s])?([\w\s]*)", li )
        assert m, \
            f"Invalid BIP-39 or SLIP-39 Mnemonic [prefix:]phrase: {li}"
        pref,mnem		= m.groups()
        if not pref and not mnem:  # blank lines ignored
            continue
        mnemonic.append( mnem.strip() )
        continuation		= pref and ( pref[-1] in MNEM_CONT )
        log.debug( f"Prefix: {pref!r:10}, Phrase: {mnem!r}" + ( "..." if continuation else "" ))
        if continuation:
            continue
        if mnemonic:
            phrase		= ' '.join( mnemonic )
            log.info( f"Mnemonic phrase: {phrase!r}" )
            yield phrase
        mnemonic		= []
    if mnemonic:
        phrase			= ' '.join( mnemonic )
        log.info( f"Mnemonic phrase: {phrase!r}" )
        yield phrase


def update_seed_data( event, window, values ):
    """Respond to changes in the desired Seed Data source, and recover/generate and update the
    -SD-SEED- text, which is a Text field (not in values), and defines the size of the Seed in hex
    nibbles.  If invalid, we will fill it with the appropriate number of '---...'.

    Stores the last known state of the -SD-... radio buttons, and saves/restores the user
    data being supplied on for BIP/SLIP/FIX.  If event indicates one of our radio-buttons, then also
    re-generate the random data.

    """
    changed			= False
    dat,pwd			= values['-SD-DATA-'],values['-SD-PASS-']
    seed_data			= window['-SD-SEED-'].get() or ''
    for src in [
            '-SD-128-RND-',
            '-SD-256-RND-',
            '-SD-512-RND-',
            '-SD-128-FIX-',
            '-SD-256-FIX-',
            '-SD-512-FIX-',
            '-SD-BIP-',
            '-SD-SLIP-',
    ]:
        # See what we got for -SD-DATA-, for this -SD-... radio button selection
        if values[src] and update_seed_data.src != src:
            # If selected radio-button for Seed Data source changed, save last source's working data
            # and restore what was, last time we were working on this source.
            if update_seed_data.src:
                update_seed_data.was[update_seed_data.src] = dat,pwd
            changed		= True
            update_seed_data.src = src
            dat,pwd		= update_seed_data.was.get( src, ('','') )
            seed_data		= ''
            window['-SD-DATA-'].update( dat )
            values['-SD-DATA-'] = dat
            window['-SD-PASS-'].update( pwd )
            # And change visibility of Seed Data source controls
            if 'FIX' in update_seed_data.src:
                window['-SD-DATA-F-'].update( "Hex data: " )
                window['-SD-DATA-F-'].update( visible=True  )
                window['-SD-PASS-C-'].update( visible=False )
                window['-SD-PASS-F-'].update( visible=False )
            elif 'BIP' in update_seed_data.src:
                window['-SD-DATA-F-'].update( "BIP-39 Mnemonic: " )
                window['-SD-DATA-F-'].update( visible=True )
                window['-SD-PASS-C-'].update( visible=False )
                window['-SD-PASS-F-'].update( visible=True )
            elif 'SLIP' in update_seed_data.src:
                window['-SD-DATA-F-'].update( "SLIP-39 Mnemonics: " )
                window['-SD-DATA-F-'].update( visible=True )
                window['-SD-PASS-C-'].update( visible=True )
                window['-SD-PASS-F-'].update( visible=values['-SD-PASS-C-'] )
            elif 'RND' in update_seed_data.src:
                window['-SD-DATA-F-'].update( visible=False )
                window['-SD-PASS-C-'].update( visible=False )
                window['-SD-PASS-F-'].update( visible=False )
        elif event == update_seed_data.src == src:
            # Same radio-button re-selected; just force an update (eg. re-generate random)
            changed		= True

    # We got our working -SD-DATA- into 'dat' (maybe from last time 'round), compute seed_data.
    status			= None
    if 'BIP' in update_seed_data.src:
        bits			= 512
        try:
            passphrase		= pwd.strip().encode( 'UTF-8' )
            seed_data		= recover_bip39(
                mnemonic	= dat.strip(),
                passphrase	= passphrase,
            )
        except Exception as exc:
            log.exception( f"BIP-39 recovery failed w/ {dat!r} w/ passphrase: {pwd!r}: {exc}" )
            status		= f"Invalid BIP-39 recovery mnemonic: {exc}"
    elif 'SLIP' in update_seed_data.src:
        bits			= 128
        window['-SD-PASS-F-'].update( visible=values['-SD-PASS-C-'] )
        try:
            passphrase		= pwd.strip().encode( 'UTF-8' )
            seed_data		= recover(
                mnemonics	= list( mnemonic_continuation( dat.strip().split( '\n' ))),
                passphrase	= passphrase,
            )
            bits		= len( seed_data ) * 4
        except Exception as exc:
            log.exception( f"SLIP-39 recovery failed w/ {dat!r} w/ passphrase: {pwd!r}: {exc}" )
            status		= f"Invalid SLIP-39 recovery mnemonics: {exc}"
    elif 'FIX' in update_seed_data.src:
        bits			= int( update_seed_data.src.split( '-' )[2] )
        try:
            # 0-fill and truncate any supplied hex data to the desired bit length
            data		= f"{dat:<0{bits // 4}.{bits // 4}}"
            seed_data 		= codecs.decode( data, 'hex_codec' )
        except Exception as exc:
            status		= f"Invalid Hex for {bits}-bit fixed seed: {exc}"
    elif changed or not seed_data:  # Random.  Regenerated each time changed, or not valid
        bits			= int( update_seed_data.src.split( '-' )[2] )
        seed_data		= random_secret( bits // 8 )
    # Compute the Seed Data as hex.  Will be 128-, 256- or 512-bit hex data.
    if status:
        seed_data		= '-' * (bits // 4)
    elif type( seed_data ) is bytes:
        seed_data		= codecs.encode( seed_data, 'hex_codec' ).decode( 'ascii' )
    # Since a window[...].update() doesn't show up to a .get() 'til the next cycle of the display,
    # we'll communicate updates to successive functions via values.
    values['-SD-SEED-'] 	= seed_data
    window['-SD-SEED-'].update( seed_data )
    return status
update_seed_data.src		= None  # noqa: E305
update_seed_data.was		= {
    '-SD-BIP-': ("zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong","")  # "<mnemnonic>","<passphrase>"
}


def stretch_seed_entropy( entropy, n, bits, encoding=None ):
    """To support the generation of a number of Seeds, each subsequent seed *must* be independent of
    the prior seed.  The Seed Data supplied (ie. recovered from BIP/SLIP-39 Mnemonics, or from fixed/random
    data) is of course unchanging for the subsequent seeds to be produced; only the "extra" Seed Entropy
    is useful for producing multiple sequential Seeds.  Returns the designated number of bits
    (rounded up to bytes).

    If non-binary hex data is supplied, encoding should be 'hex_codec' (0-filled/truncated on the
    right up to the required number of bits); otherwise probably 'UTF-8' (and we'll always stretch
    other encoded Entropy, even for the first (ie. 0th) seed).

    If binary data is supplied, it must be sufficient to provide the required number of bits for the
    first and subsequent Seeds (SHA-512 is used to stretch, so any encoded and stretched entropy
    data will be sufficient)

    """
    assert n == 0 or ( entropy and n >= 0 ), \
        f"Some Extra Seed Entropy is required to produce the {ordinal(n+1)}+ Seed(s)"
    assert ( type(entropy) is bytes ) == ( not encoding ), \
        "If non-binary Seed Entropy is supplied, an appropriate encoding must be specified"
    if encoding:
        if encoding == 'hex_codec':
            # Hexadecimal Entropy was provided; Use the raw encoded Hex data for the first round!
            entropy		= f"{entropy:<0{bits // 4}.{bits // 4}}"
            entropy		= codecs.decode( entropy, encoding )  # '012abc' --> b'\x01\x2a\xbc'
        else:
            # Other encoding was provided, eg 'UTF-8', 'ASCII', ...; stretch for the 0th Seed, too.
            n		       += 1
            entropy		= codecs.encode( entropy, encoding )    # '012abc' --> b'012abc'
    for _ in range( n ):
        entropy			= hashlib.sha512( entropy ).digest()
    octets			= ( bits + 7 ) // 8
    assert len( entropy ) >= octets, \
        "Insufficient extra Seed Entropy provided for {ordinal(n+1)} {bits}-bit Seed"
    return entropy[:octets]


def update_seed_entropy( window, values ):
    """Respond to changes in the extra Seed Entropy, and recover/generate the -SE-SEED-.  It is
    expected to be exactly the same size as the -SD-SEED- data.  Stores the last known state of the
    -SE-... radio buttons, updating visibilties on change.

    """
    dat				 = values['-SE-DATA-']
    for src in [
        '-SE-NON-',
        '-SE-HEX-',
        '-SE-SHA-',
    ]:
        if values[src] and update_seed_entropy.src != src:
            # If selected radio-button for Seed Entropy source changed, save last source's working
            # data and restore what was, last time we were working on this source.
            if update_seed_entropy.src:
                update_seed_entropy.was[update_seed_entropy.src] = dat
            dat			= update_seed_entropy.was.get( src, '' )
            update_seed_entropy.src = src
            window['-SE-DATA-'].update( dat )
            values['-SE-DATA-']	= dat
            if 'HEX' in update_seed_entropy.src:
                window['-SE-DATA-T-'].update( "Hex digits: " )
            else:
                window['-SE-DATA-T-'].update( "Die rolls, etc.: " )

    status			= None
    seed_data			= values.get( '-SD-SEED-', window['-SD-SEED-'].get() )
    bits			= len( seed_data ) * 4
    log.debug( f"Computing Extra Entropy, for {bits}-bit Seed Data: {seed_data!r}" )
    if 'NON' in update_seed_entropy.src:
        window['-SE-DATA-F-'].update( visible=False )
        extra_entropy		= b''
    elif 'HEX' in update_seed_entropy.src:
        window['-SE-DATA-F-'].update( visible=True )
        try:
            # 0-fill and truncate any supplied hex data to the desired bit length
            extra_entropy	= stretch_seed_entropy( dat, n=0, bits=bits, encoding='hex_codec' )
        except Exception as exc:
            status		= f"Invalid Hex {dat!r} for {bits}-bit extra seed entropy: {exc}"
    else:
        window['-SE-DATA-F-'].update( visible=True )
        try:
            # SHA-512 stretch and possibly truncate supplied Entropy (show for 1st Seed)
            extra_entropy	= stretch_seed_entropy( dat, n=0, bits=bits, encoding='UTF-8' )
        except Exception as exc:
            status		= f"Invalid data {dat!r} for {bits}-bit extra seed entropy: {exc}"

    # Compute the Seed Entropy as hex.  Will be 128-, 256- or 512-bit hex data.
    if status or not extra_entropy:
        extra_entropy		= '-' * (bits // 4)
    elif type( extra_entropy ) is bytes:
        extra_entropy		= codecs.encode( extra_entropy, 'hex_codec' ).decode( 'ascii' )
    values['-SE-SEED-']		= extra_entropy
    window['-SE-SEED-'].update( extra_entropy )
update_seed_entropy.src	= None  # noqa: E305
update_seed_entropy.was = {}


def compute_master_secret( window, values, n=0 ):
    """Validate the Seed Data and Seed Entropy, and compute the n'th master secret seed.  This is a
    simple XOR of the Seed Data, and any extra Seed Entropy -- so that the user can VISUALLY OBSERVE
    that the purported Seed Data and their provided extra Seed Entropy leads to the final master
    secret seed.

    This is a critical feature -- without this visual confirmation, it is NOT POSSIBLE to trust any
    cryptocurrency seed generation algorithm.

    This function must have knowledge of the extra Seed Entropy settings, so it inspects the
    -SE-{NON/HEX}- checkbox values.
    """
    seed_data_hex		= values.get( '-SD-SEED-', window['-SD-SEED-'].get() )
    bits			= len( seed_data_hex ) * 4
    assert bits in BITS, \
        f"Invalid {bits}-bit Seed size: {seed_data_hex}"
    try:
        seed_data		= codecs.decode( seed_data_hex, 'hex_codec' )
    except Exception as exc:
        raise ValueError( f"Invalid Seed hex data: {seed_data_hex}" ) from exc
    if values['-SE-NON-']:
        assert n == 0, \
            f"Some Extra Seed Entropy (select and enter above) required for {ordinal(n+1)} {bits}-bit Seed"
        master_secret		= seed_data
    else:
        encoding 		= 'hex_codec' if values['-SE-HEX-'] else 'UTF-8'
        seed_entr		= stretch_seed_entropy( values['-SE-DATA-'], n=n, bits=bits, encoding=encoding )
        master_secret		= bytes( d ^ e for d,e in zip( seed_data, seed_entr ) )
    return master_secret


def update_seed_recovered( window, values, details, passphrase=None ):
    """Display the SLIP39 Mnemonics.  Each mnemonic word is maximum 8 characters in length, separated
    by a single space.  The bit- and word-length of each standard SLIP39 Mnemonic is:

        bits words
        ---- -----
        128  20
        256  33
        512  59

    There must always be a passphrase; it may be empty (b'').

    """
    mnemonics			= []
    rows			= []
    for g,(g_of,g_mnems) in details.groups.items() if details else []:
        for i,mnem in enumerate( g_mnems, start=1 ):
            mnemonics.append( mnem )
            # Display Mnemonics in rows of 20, 33 or 59 words:
            #    1: single line mnemonic ...
            # or
            #    2/ word something another ...
            #     \ last line of mnemonic ...
            # or
            #    3/ word something another ...
            #     | another more ...
            #     \ last line of mnemonic ...
            mset		= mnem.split()
            for mri,mout in enumerate( chunker( mset, 20 )):
                p		= MNEM_PREFIX.get( len(mset), '' )[mri:mri+1] or ':'
                rows.append( f"{g:<8.8}" + f"{i:2}{p} " + ' '.join( f"{m:<8}" for m in mout ))
                g		= ''
                i		= ''

    window['-MNEMONICS-'+sg.WRITE_ONLY_KEY].update( '\n'.join( rows ))

    recohex			= ''
    if mnemonics:
        reco			= recover( mnemonics, passphrase=passphrase or b'' )
        recohex			= codecs.encode( reco, 'hex_codec' ).decode( 'ascii' )
    window['-SEED-RECOVERED-'].update( recohex )

    # Ensure that our recovered Seed matches the computed Seed!
    if window['-SEED-'].get() != recohex:
        return f"Recovered Seed {recohex!r} doesn't match expected: {window['-SEED-'].get()!r}"


def user_name_full():
    full_name			= None
    if sys.platform == 'darwin':
        command			= [ '/usr/sbin/scutil' ]
        command_input		= "show State:/Users/ConsoleUser"
    elif sys.platform == 'win32':
        command			= [ 'net', 'user', os.environ['USERNAME'] ]
        command_input		= None
    else:  # assume *nix
        command			= [ 'getent', 'passwd', os.environ['USER'] ]
        command_input		= None

    subproc			= subprocess.run(
        command,
        input		= command_input,
        capture_output	= True,
        encoding	= 'UTF-8',
    )
    assert subproc.returncode == 0 and subproc.stdout, \
        f"{' '.join( command )!r} command failed, or no output returned"

    if sys.platform == 'darwin':
        for li in subproc.stdout.split( '\n' ):
            if 'kCGSessionLongUserNameKey' in li:
                # eg.: "      kCGSessionLongUserNameKey : Perry Kundert"
                full_name	= li.split( ':' )[1].strip()
                break
    elif sys.platform == 'win32':
        for li in subproc.stdout.split( '\n' ):
            if li.startswith( 'Full Name' ):
                # eg.: "Full Name                IEUser"
                full_name	= li[9:].strip()
                break
    else:
        # getent="perry:x:1002:1004:Perry Kundert,,,:/home/perry:/bin/bash"
        # >>> getent.split(':')
        # ['perry', 'x', '1002', '1004', 'Perry Kundert,,,', '/home/perry', '/bin/bash']
        pwents			= subproc.stdout.split( ':' )
        assert len( pwents ) > 4, \
                f"Unrecognized passwd entry: {li}"
        gecos			= pwents[4]
        full_name		= gecos.split( ',' )[0]  # Discard ...,building,room,phone,...

    assert full_name, \
        "User's full name not found"
    log.info( f"Current user's full name: {full_name!r}" )
    return full_name


def app(
    names			= None,
    group			= None,
    threshold			= None,
    cryptocurrency		= None,
    edit			= None,
    passphrase			= None,
    scaling			= None,
    no_titlebar			= False,
):
    """Convert sequence of group specifications into standard { "<group>": (<needs>, <size>) ... }"""

    if isinstance( group, dict ):
        groups			= group
    else:
        groups			= dict(
            group_parser( g )
            for g in group or GROUPS
        )
    assert groups and all( isinstance( k, str ) and len( v ) == 2 for k,v in groups.items() ), \
        f"Each group member specification must be a '<group>': (<needs>, <size>) pair, not {type(next(groups.items()))}"

    group_threshold		= int( threshold ) if threshold else math.ceil( len( groups ) * GROUP_THRESHOLD_RATIO )

    sg.theme( 'DarkAmber' )

    # Try to set a sane initial CWD (for saving generated files).  If we start up in the standard
    # macOS App's "Container" directory for this App, ie.:
    #
    #    /Users/<somebody>/Library/Containers/ca.kundert.perry.SLIP39/Data
    #
    # then we'll move upwards to the user's home directory.  If we change the macOS App's Bundle ID,
    # this will change..
    cwd				= os.getcwd()
    if cwd.endswith( '/Library/Containers/ca.kundert.perry.SLIP39/Data' ):
        cwd			= cwd[:-48]
    sg.user_settings_set_entry( '-target folder-', cwd )

    #
    # If no name(s) supplied, try to get the User's full name.
    #
    if not names:
        try:
            names		= [ user_name_full() ]
        except Exception as exc:
            logging.exception( f"Failed to discover user full name: {exc}" )

    # If we cannot support the output of Paper Wallets, disable
    wallet_pwd			= None if paper_wallet_available() else False
    wallet_pwd_hint		= None
    wallet_derive		= None  # A derivation path "edit", if any
    window			= None
    status			= None
    status_error		= False
    event			= False
    events_termination		= (sg.WIN_CLOSED, 'Exit',)
    events_ignored		= ('-MNEMONICS-'+sg.WRITE_ONLY_KEY,)
    master_secret		= None		# default to produce randomly
    details			= None		# The SLIP-39 details produced from groups; make None to force SLIP-39 Mnemonic update
    cryptopaths			= None
    timeout			= 0		# First time thru; refresh immediately
    controls			= 0		# What level of controls complexity is desired?
    instructions		= ''		# The last instructions .txt payload found
    while event not in events_termination:
        # A Controls layout selection, eg. '-LO-2-'; closes and re-generates window layout
        if event and event.startswith( '-LO-' ):
            controls		= int( event.split( '-' )[2] )
            window.close()
            window		= None

        # Create window (for initial window.read()), or update status
        if window:
            window['-STATUS-'].update( f"{status or 'OK'}", font=font_bold if status_error else font )
            window['-RECOVERY-'].update( f"of {len(groups)}" )
            # All main window rows are assumed to be frames, was: window['-SD-SEED-F-'].expand( expand_x=True ), ...
            for frame in window.Rows:
                if frame and frame[0].visible:
                    frame[0].expand( expand_x=True )
        else:
            # Compute App window layout, from the supplied groups and controls selection.  For
            # printers, an empty list is OK (we can still print to the default printer).  However,
            # if we fail to successfully obtain any printer information (cannot talk to the printer
            # subsystem, then we'll disable "Print" w/ printers=None)
            try:
                printers	= list( human for system,human in printers_available() )
            except Exception as exc:
                log.exception( f"Failed to find printers: {exc}" )
                printers	= None

            layout		= groups_layout(
                names		= names,
                group_threshold	= group_threshold,
                groups		= groups,
                cryptocurrency	= cryptocurrency,
                passphrase	= passphrase,
                wallet_pwd	= wallet_pwd,
                wallet_pwd_hint	= wallet_pwd_hint,
                wallet_derive	= wallet_derive,
                controls	= controls,
                printers	= printers,
            )
            window		= sg.Window(
                f"{', '.join( names )} SLIP-39 Mnemonic Cards",
                layout,
                finalize	= True,
                grab_anywhere	= True,
                no_titlebar	= no_titlebar,
                scaling		= scaling,
            )
            timeout		= 0 		# First time through w/ new window, refresh immediately

        # Block (except for first loop) and obtain current event and input values. Until we get a
        # new event, retain the current status
        event, values		= window.read( timeout=timeout )
        timeout			= None 		# Subsequently, default; block indefinitely
        logging.debug( f"{event}, {values}" )
        if not values or event in events_termination or event in events_ignored:
            continue

        status			= None
        status_error		= True

        # See if there are any instructional 'SLIP-39-<event>.txt' for the last event.  If so, load
        # it into the '-INSTRUCTIONS-' Multiline.  We'll split each event on its component '-', and
        # look for eg. SLIP-39-LO.txt, when we see event == '-LO-1-'.  We'll select the most
        # specific instructional .txt we can load.  Only if the current instructions is empty will
        # we go all the way back to load the generic SLIP-39.txt.
        txt_segs		= ( event or '' ).strip('-').split( '-' )
        for txt_i in range( len( txt_segs ), 0 if instructions else -1, -1 ):
            txt_name		= '-'.join( [ 'SLIP', '39' ] + txt_segs[:txt_i] ) + '.txt'
            txt_path		= os.path.join( os.path.dirname( __file__ ), txt_name )
            try:
                with open( txt_path, 'r', encoding='utf-8' ) as txt_f:
                    txt		= txt_f.read()
                    if txt:
                        instructions = txt
                        break
            except FileNotFoundError:
                pass
        window['-INSTRUCTIONS-'].update( instructions )

        if event == '+' and len( groups ) < 16:
            # Add a SLIP39 Groups row (if not already at limit)
            g			= len( groups )
            name		= f"Group{g+1}"
            needs		= (2,3)
            groups[name] 	= needs
            window.close()
            window		= None
            continue

        # Deduce the desired Seed names, defaulting to "SLIP39"; if any change, force update of
        # details.  If the user specifies more than one, ensure that Extra Seed Entropy is enabled.
        names_now		= [
            name.strip()
            for name in ( values['-NAMES-'].strip() or "SLIP39" ).split( ',' )
            if name and name.strip()
        ]
        if names != names_now:
            names		= names_now
            details		= None
            if names and len( names ) > 1:
                if values['-SE-NON-']:
                    # Multiple names specified, but NO Extra Seed Entropy selected!
                    window['-SE-SHA-'].update( True )
                    timeout	= 0
                    continue

        # Attempt to compute the 1st Master Secret Seed, collecting any failure status detected.
        # Compute the Master Secret Seed, from the supplied Seed Data and any extra Seed Entropy.
        # We are displaying the 1st extra Seed Entropy, used to produce the first Seed, for the
        # first SLIP-39 encoding.
        master_secret_was	= window['-SEED-'].get()
        status_sd		= update_seed_data( event, window, values )
        status_se		= update_seed_entropy( window, values )
        status_ms		= None
        try:
            master_secret	= compute_master_secret( window, values, n=0 )
        except Exception as exc:
            status_ms		= f"Error computing master_secret: {exc}"
            logging.exception( f"{status}" )
            master_secret	= '-' * len( values['-SD-SEED-'] )
        if type(master_secret) is bytes:
            master_secret	= codecs.encode( master_secret, 'hex_codec' ).decode( 'ascii' )

        # From this point forward, detect if we have seen any change in the computed Master Seed, or
        # in the SLIP-39 groups recovered; avoid unnecessary update of the SLIP-39 Mnemonics.  And,
        # if any status was reported in the computation of Seed Data, extra Seed Entropy or Master
        # Secret, report it now.
        if master_secret != master_secret_was:
            window['-SEED-'].update( master_secret )
            log.info( "Updating SLIP-39 due to changing Master Seed" )
            details		= None
        status			= status_sd or status_se or status_ms
        if status:
            update_seed_recovered( window, values, None )
            continue

        # Collect up the specified Group names; ignores groups with an empty name (effectively
        # eliminating that group)
        g_rec			= {}
        status			= None
        for g in range( 16 ):
            grp_idx		= f"-G-NAME-{g}"
            if grp_idx not in values:
                break
            grp			= '?'
            try:
                grp		= str( values[grp_idx] ).strip()
                if not grp:
                    continue
                assert grp not in g_rec, \
                    f"Duplicate group name {grp}"
                g_rec[grp] 	= int( values[f"-G-NEED-{g}"] or 0 ), int( values[f"-G-SIZE-{g}"] or 0 )
            except Exception as exc:
                status		= f"Error defining group {g+1} {grp!r}: {exc}"
                logging.exception( f"{status}" )
                update_seed_recovered( window, values, None )
                continue

        if g_rec != groups:  # eg. group name or details changed
            log.info( "Updating SLIP-39 due to changing Groups" )
            groups		= g_rec
            details		= None

        # Confirm the selected Group Threshold requirement
        try:
            g_thr_val		= values['-THRESHOLD-']
            g_thr		= int( g_thr_val )
            assert 0 < g_thr <= len( groups ), \
                f"Group threshold must be an integer between 1 and the number of groups ({len(groups)})"
        except Exception as exc:
            status		= f"Error defining group threshold {g_thr_val!r}: {exc}"
            logging.exception( f"{status}" )
            update_seed_recovered( window, values, None )
            details		= None
            continue
        if g_thr != group_threshold:
            log.info( "Updating SLIP-39 due to changing Group Threshold" )
            group_threshold	= g_thr
            details		= None

        # See if a derivation path edit is provided; doesn't support specifying an entire derivation
        # path, just a number:
        #
        #    1 or '' ->  ../-0
        #    3       ->  ../-2
        #
        # or a derivation path edit like:
        #
        #    ../3'/0/-9
        #
        wallet_derive = edit_rec = values['-WALLET-DERIVE-']
        try:
            n			= 1
            if edit_rec:
                n		= int( edit_rec )
        except ValueError:
            pass
        else:
            if n <= 0:
                status		= f"At least 1 Cryptocurrency address must be derived, not: {edit_rec}"
                update_seed_recovered( window, values, None )
                details		= None
                continue
            edit_rec		= f"-{n-1}"
        if not edit_rec.lstrip('.').startswith('/'):
            edit_rec		= '/' + edit_rec
        while not edit_rec.startswith('..'):
            edit_rec		= '.' + edit_rec
        if edit_rec != edit:
            log.info( "Updating SLIP-39 due to changing Derivation path changes" )
            edit		= edit_rec
            details		= None

        # See what Cryptocurrencies and Paper Wallets are desired, by what checkboxes are clicked.
        # If none are, then the default (BTC, ETH) will be defaulted.
        cs_rec			= set( c for c in Account.CRYPTOCURRENCIES if values.get( f"-CRYPTO-{c}-" ) )
        cps_rec			= cryptopaths_parser( cryptocurrency=cs_rec, edit=edit )
        if cs_rec != cryptocurrency or cps_rec != cryptopaths:
            log.info( "Updating SLIP-39 due to changing Cryptocurrencies" )
            cryptocurrency	= cs_rec
            cryptopaths		= cps_rec
            details		= None

        # Produce a summary of the SLIP-39 recovery groups, including any passphrase needed for
        # decryption of the SLIP-39 seed, and how few/many cards will need to be collected to
        # recover the Seed.  If the SLIP-39 passphrase has changed, force regeneration of SLIP-39.
        # NOTE: this SLIP-39 standard passphrase is NOT Trezor-compatible; use the Trezor "hidden
        # wallet" feature instead.
        summary_groups		= ', '.join( f"{n}({need}/{size})" for n,(need,size) in groups.items())
        summary			= f"Recovery needs {group_threshold} of {len(groups)} Groups: {summary_groups}"

        tot_cards		= sum( size for _,size in groups.values() )
        min_req			= sum( islice( sorted( ( need for need,_ in groups.values() ), reverse=False ), group_threshold ))
        max_req			= sum( islice( sorted( ( need for need,_ in groups.values() ), reverse=True  ), group_threshold ))
        summary		       += f" (from {min_req}-{max_req} of {tot_cards} Mnemonic cards)"

        if values['-PASSPHRASE-C-']:
            window['-PASSPHRASE-F-'].update( visible=True )
            passphrase_now	= values['-PASSPHRASE-'].strip()
            if passphrase_now:
                summary	       += f", w/ passphrase: {passphrase_now!r})"
            passphrase_now	= passphrase_now.encode( 'UTF-8' )
            if passphrase != passphrase_now:
                passphrase	= passphrase_now
                details		= None
        else:
            window['-PASSPHRASE-F-'].update( visible=False )
            if passphrase:
                details		= None
            passphrase		= b''

        window['-SUMMARY-'].update( summary )

        # Re-compute the SLIP39 Seed details.  For multiple names, each subsequent slip39.create
        # uses a master_secret produced by hashing the prior master_secret entropy.  For the 1st
        # Seed, we've computed the master_secret, above.  Each master_secret_n contains the computed
        # Seed combining Seed Data and (any) Seed Entropy, stretched for the n'th Seed.  If there is
        # no extra Seed Entropy, we will fail to produce subsequent seeds.  Recompute the desired
        # cryptopaths w/ any path adjusts, in case derivation of multiple Paper Wallets is desired.
        #
        # We avoid recomputing this unless something about the seed or the recovered groups changes; each
        # time we recompute -- even without any changes -- the SLIP-39 Mnemonics will change, due to the use
        # of entropy in the SLIP-39 process.
        if not details or names[0] not in details:
            log.info( f"SLIP39 details for {names}..." )
            try:
                details		= {}
                for n,name in enumerate( names ):
                    master_secret_n	= compute_master_secret( window, values, n=n )
                    assert n > 0 or codecs.encode( master_secret_n, 'hex_codec' ).decode( 'ascii' ) == master_secret, \
                        "Computed Seed for 1st SLIP39 Mnemonics didn't match"
                    log.info( f"SLIP39 for {name} from master_secret: {codecs.encode( master_secret_n, 'hex_codec' ).decode( 'ascii' )} (w/ passphrase: {passphrase!r}" )
                    details[name]	= create(
                        name		= name,
                        group_threshold	= group_threshold,
                        master_secret	= master_secret_n,
                        groups		= groups,
                        cryptopaths	= cryptopaths,
                        passphrase	= passphrase,
                    )
            except Exception as exc:
                status		= f"Error creating: {exc}"
                logging.exception( f"{status}" )
                update_seed_recovered( window, values, None )
                details		= None
                continue

        # Display the computed SLIP-39 Mnemonics for the first name.  We know names[0] is in details...
        if status := update_seed_recovered( window, values, details[names[0]], passphrase=passphrase ):
            details		= None
            continue

        # If all has gone well -- display the resultant <name>/<filename>, and some derived account details
        name_len		= max( len( name ) for name in details )
        status			= '\n'.join(
            f"{name:>{name_len}} == {', '.join( f'{a.crypto} @ {a.path}: {a.address}' for a in details[name].accounts[0] ):.120}..."
            for name in details
        )

        # We have a complete SLIP-39 Mnemonic set.  If we get here, no failure status has been
        # detected, and SLIP39 mnemonic and account details { "name": <details> } have been created;
        # we can now save the PDFs; converted details is now { "<filename>": <details> })
        if wallet_pwd is not False:
            # And, if Paper Wallets haven't been disabled completely, remember our password/hint
            wallet_pwd		= values['-WALLET-PASS-']  # Produces Paper Wallet(s) iff set
            wallet_pwd_hint	= values['-WALLET-HINT-']
        if event in ('-SAVE-', '-PRINT-'):
            # A -SAVE- target directory has been selected; use it, if possible.  This is where any
            # output will be written.  It should usually be a removable volume, but we do not check.
            # An empty path implies the current directory.
            filepath,printer	= None,None
            if event == '-SAVE-':
                filepath	= values['-SAVE-']
                log.info( f"Saving to {filepath!r}..." )
            if event == '-PRINT-':
                printer		= values['-PRINTER-']
                log.info( f"Printing to {printer!r}..." )
            try:
                card_format	= next( c for c in CARD_SIZES if values[f"-CS-{c}-"] )
                paper_format	= next( pf for pn,pf in PAPER_FORMATS.items() if values[f"-PF-{pn}-"] )
                details		= write_pdfs(
                    names		= details,
                    card_format		= card_format,
                    paper_format	= paper_format,
                    cryptocurrency	= cryptocurrency,
                    edit		= edit,
                    wallet_pwd		= wallet_pwd,
                    wallet_pwd_hint	= wallet_pwd_hint,
                    wallet_format	= next( (f for f in WALLET_SIZES if values.get( f"-WALLET-SIZE-{f}-" )), None ),
                    filepath		= filepath,
                    printer		= printer,
                )
            except Exception as exc:
                status		= f"Error saving PDF(s): {exc}"
                logging.exception( f"{status}" )
                continue
            name_len		= max( len( name ) for name in details )
            status		= '\n'.join(
                f"Saved {name}"
                for name in details
            )
        # Finally, success has been assured; turn off emboldened status line
        status_error		= False

    window.close()


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Graphical User Interface to create and output SLIP-39 encoded Seeds and Paper Wallets to a PDF file.",
        formatter_class = argparse.RawDescriptionHelpFormatter,
        epilog = """\

A GUI App for creating SLIP-39 Mnemonic encoded cryptocurrency wallet seeds, either from secure
randomness, or from pre-existing seed entropy, or recovered from prior SLIP-39 or BIP-39 encoded
seed Mnemonics.

This can be useful for converting existing BIP-39 Mnemonic encoded seeds to more secure and
recoverable SLIP-39 Mnemonic encoding.

"""
    )
    ap.add_argument( '-v', '--verbose', action="count",
                     default=0,
                     help="Display logging information." )
    ap.add_argument( '-q', '--quiet', action="count",
                     default=0,
                     help="Reduce logging output." )
    ap.add_argument( '-t', '--threshold',
                     default=None,
                     help="Number of groups required for recovery (default: half of groups, rounded up)" )
    ap.add_argument( '-g', '--group', action='append',
                     help="A group name[[<require>/]<size>] (default: <size> = 1, <require> = half of <size>, rounded up, eg. 'Frens(3/5)' )." )
    ap.add_argument( '-c', '--cryptocurrency', action='append',
                     default=[],
                     help="A crypto name and optional derivation path ('../<range>/<range>' allowed); defaults:" + ', '.join(
                         f'{c}:{Account.path_default(c)}' for c in Account.CRYPTO_NAMES.values()
                     ))
    ap.add_argument( '-p', '--path',
                     default=None,
                     help="Modify all derivation paths by replacing the final segment(s) w/ the supplied range(s), eg. '.../1/-' means .../1/[0,...)")
    ap.add_argument( '--passphrase',
                     default=None,
                     help="Encrypt the master secret w/ this passphrase, '-' reads it from stdin (default: None/'')" )
    ap.add_argument( '-s', '--scaling',
                     default=1, type=float,
                     help="Scaling for display (eg. 1.5, 0.5 for high-resolution displays), if not automatically detected")
    ap.add_argument( '--no-titlebar', default=False, action='store_true',
                     help="Avoid displaying a title bar and border on main window" )
    ap.add_argument( 'names', nargs="*",
                     help="Account names to produce")
    args			= ap.parse_args( argv )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    log_cfg['level']		= log_level( args.verbose - args.quiet )
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    if sys.platform == 'win32':
        # Establishes a common baseline size on macOS and Windows, as long as
        # SetProcessDpiAwareness( 1 ) is set, and scaling == 1.0.  Ignored on macOS.
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)

    try:
        app(
            names		= args.names,
            threshold		= args.threshold,
            group		= args.group,
            cryptocurrency	= args.cryptocurrency,
            edit		= args.path,
            passphrase		= args.passphrase,
            no_titlebar		= args.no_titlebar,
            scaling		= args.scaling,
        )
    except Exception as exc:
        log.exception( f"Failed running App: {exc}" )
        return 1
    return 0
