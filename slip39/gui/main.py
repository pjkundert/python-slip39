
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

from __future__         import annotations

import argparse
import codecs
import logging
import math
import os
import pprint
import re
import sys
import subprocess

from itertools		import islice

import PySimpleGUI as sg

from ..api		import Account, create, group_parser, random_secret, cryptopaths_parser, paper_wallet_available, stretch_seed_entropy
from ..recovery		import recover, recover_bip39, produce_bip39, scan_entropy, display_entropy
from ..util		import log_level, log_cfg, ordinal, commas, chunker, hue_shift, rate_dB, entropy_rating_dB, timing, avg, parse_scutil
from ..layout		import write_pdfs, printers_available
from ..defaults		import (
    GROUPS, GROUP_THRESHOLD_RATIO, MNEM_PREFIX, CRYPTO_PATHS, BITS, BITS_BIP39, BITS_DEFAULT,
    CARD_SIZES, CARD, PAPER_FORMATS, PAPER, WALLET_SIZES, WALLET, MNEM_CONT, THEME,
    LAYOUT, LAYOUT_OPTIONS, LAYOUT_BAK, LAYOUT_CRE, LAYOUT_REC, LAYOUT_PRO
)

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( __package__ )


BIP39_EXAMPLE_128		= "zoo " * 11 + "wrong"
BIP39_EXAMPLE_256		= "zoo " * 23 + "vote"
SLIP39_EXAMPLE_128              = "academic acid acrobat romp change injury painting safari drug browser" \
                                  " trash fridge busy finger standard angry similar overall prune ladybug" \
                                  "\n" \
                                  "academic acid beard romp believe impulse species holiday demand building" \
                                  " earth warn lunar olympic clothes piece campus alpha short endless"

SD_SEED_FRAME			= 'Seed Source: Create your Seed Entropy here'
SE_SEED_FRAME			= 'Seed Extra Randomness'
SS_SEED_FRAME			= 'Seed Secret & SLIP-39 Recovery Groups'


def pretty(thing, maxstr=60, indent=4, **kwds):
    class P(pprint.PrettyPrinter):
        def _format(self, thing, *args, **kwds):
            if isinstance(thing, str) and len(thing) > maxstr:
                thing = thing[:maxstr//2] + '…' + thing[-maxstr//2:]
            return super()._format(thing, *args, **kwds)

    return P(indent=indent, **kwds).pformat(thing)


def theme_color( thing, theme=None ):
    """Get the currency configured PySimpleGUI Theme color for thing == eg. "TEXT", "BACKGROUND.
    """
    if theme is None:
        theme			= sg.CURRENT_LOOK_AND_FEEL
    return sg.LOOK_AND_FEEL_TABLE[theme][thing]


# Try to pick a font; Use something like this to see what's available (ya, this sucks):
#
#     from tkinter import Tk, font
#     root = Tk()
#     font_tuple = font.families()
#     #Creates a Empty list to hold font names
#     FontList=[]
#     fonts = [font.Font(family=f) for f in font.families()]
#     monospace = [f for f in fonts if f.metrics("fixed")]
#     for font in monospace:
#         FontList.append(font.actual('family'))
#     root.destroy()
#     print( '\n'.join( FontList ))
if sys.platform == 'darwin':
    font_name			= 'Andale Mono'
elif sys.platform == 'win32':
    font_name			= 'Consolas'
else:  # assume linux
    font_name			= 'DejaVu Sans Mono'

font_points			= 14
font				= (font_name, font_points+0)
font_dense			= (font_name, font_points-2)
font_small			= (font_name, font_points-4)
font_big			= (font_name, font_points+2)
font_bold			= (font_name, font_points+2, 'bold italic')

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


def T_hue( kwds, shift ):
    return dict(
        kwds,
        text_color		= hue_shift( theme_color( 'TEXT' ),       shift=shift ),
        background_color	= hue_shift( theme_color( 'BACKGROUND' ), shift=shift ),
    )


T_kwds_dense			= dict(
    font		= font_dense,
)
F_kwds				= dict(
    font		= font,
)
F_kwds_big			= dict(
    F_kwds,
    font		= font_big,
)
B_kwds				= dict(
    font		= font,
    enable_events	= True,
)

prefix				= (18, 1)
inputs				= (40, 1)
inlong				= (128,1)       # 512-bit seeds require 128 hex nibbles
shorty				= (10, 1)
tiny				= ( 3, 1)
mnemos				= (192,3)

passphrase_trezor_incompatible	= 'SLIP-39 Passphrase; NOT Trezor compatible; use "Hidden wallet"?'


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
        sg.Frame( '# cards', [
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

    # Select Controls complexity.
    LO				= LAYOUT_OPTIONS[controls] if controls is not None else LAYOUT
    controls			= LAYOUT_OPTIONS.index( LO )
    assert controls >= 0, f"Invalid controls index {controls}"
    LO_BAK			= controls == LAYOUT_BAK		# True iff LO == Backup (simplest)
    LO_CRE			= controls >= LAYOUT_CRE		# True iff non-Backup (usual)
    LO_REC			= controls >= LAYOUT_REC		# True iff LO == Recover or Pro
    LO_PRO			= controls == LAYOUT_PRO		# True iff LO == Pro

    CRYPTO_DISPLAY		= list(
        symbol
        for symbol in Account.CRYPTO_NAMES.values()  # Retains desired ordering (vs. CRYPTOCURRENCIES set)
        if LO_PRO or symbol not in Account.CRYPTOCURRENCIES_BETA
    )

    layout                      = [
        [
            sg.Frame( 'Seed Name & Format for SLIP-39 Recovery Cards', [
                [
                    sg.Column( [
                        [
                            sg.Text( f"Seed Name{LO_PRO and 's, ...' or ''}:",  size=prefix,    **T_kwds ),
                            sg.Input( f"{', '.join(names)}",key='-NAMES-',      size=inputs,    **I_kwds ),
                            sg.Checkbox( '2-Sided',key='-PF-DOUBLE-',		default=True,	**I_kwds ),
                        ],
                        [
                            sg.Text( "Card size:",                                              **T_hue( T_kwds, 1/20 )),
                        ] + [
                            sg.Radio( f"{cs}",     "CS", key=f"-CS-{cs}-",      default=(cs == CARD),
                                                                                                **T_hue( B_kwds, 1/20 ))
                            for ci,cs in enumerate( CARD_SIZES )
                            if LO_PRO or ( LO_REC and cs.lower() != "photo"  ) or ci < len( CARD_SIZES ) // 2
                        ]
                    ] ),
                    sg.Column( [
                        [
                            sg.Text( "Controls:",                                                **T_hue( T_kwds, 2/20 )),
                        ] + [
                            sg.Radio( f"{lo:7}",  "LO", key=f"-LO-{li}-",    default=(lo == LO), **T_hue( B_kwds, 2/20 ))  # eg. -LO-1-
                            for li,lo in enumerate( LAYOUT_OPTIONS )
                        ],
                        [
                            sg.Text( "on Paper:",                                               **T_hue( T_kwds, 3/20 )),
                        ] + [
                            sg.Radio( f"{pf:7}",  "PF", key=f"-PF-{pf}-", default=(pf == PAPER), **T_hue( B_kwds, 3/20 ))
                            for pi,pf in enumerate( PAPER_FORMATS )
                            if LO_PRO or ( LO_REC and pf.lower() != "photo" ) or pi < len( PAPER_FORMATS ) // 2
                        ],
                    ] )
                ]
            ],                                          key='-OUTPUT-F-',                       **F_kwds_big ),
        ],
    ] + [
        [
            # SLIP-39 only available in Recovery; SLIP-39 Passphrase only in Pro; BIP-39 and Fixed Hex only in Pro
            sg.Frame( SD_SEED_FRAME, [
                [
                    sg.Text( "Random:" if not LO_BAK else "Source:",            visible=LO_CRE, **T_hue( T_kwds, 0/20 )),
                    sg.Radio( "128-bit",          "SD", key='-SD-128-RND-',     default=LO_CRE,
                                                                                visible=LO_CRE, **T_hue( B_kwds, 0/20 )),
                    sg.Radio( "256-bit",          "SD", key='-SD-256-RND-',     visible=LO_CRE, **T_hue( B_kwds, 0/20 )),
                    sg.Radio( "512-bit",          "SD", key='-SD-512-RND-',     visible=LO_PRO, **T_hue( B_kwds, 0/20 )),
                    sg.Text( "Recover:",                                        visible=LO_CRE, **T_hue( T_kwds, 2/20 )),
                    sg.Radio( "SLIP-39",          "SD", key='-SD-SLIP-',        visible=LO_REC, **T_hue( B_kwds, 2/20 )),
                    sg.Radio( "BIP-39",           "SD", key='-SD-BIP-',         default=LO_BAK,
                                                                                visible=LO_CRE, **T_hue( B_kwds, 2/20 )),
                    sg.Radio( "BIP-39 Seed",      "SD", key='-SD-BIP-SEED-',    visible=LO_PRO, **T_hue( B_kwds, 2/20 )),
                    sg.Checkbox( 'Passphrase',          key='-SD-PASS-C-',      visible=False,  **T_hue( B_kwds, 2/20 )),
                ],
                [
                    sg.Frame( passphrase_trezor_incompatible, [
                        [
                            sg.Text( "Passphrase (decrypt): ",                                  **T_kwds ),
                            sg.Input( "",               key='-SD-PASS-',        size=inputs,    **I_kwds ),
                        ],
                    ],                                  key='-SD-PASS-F-',      visible=False,  **F_kwds ),
                ],
                [
                    sg.Frame( 'From Mnemonic(s):', [
                        [
                            sg.Multiline( "",           key='-SD-DATA-',        size=mnemos,
                                          no_scrollbar=True,                                    **I_kwds_small ),
                        ],
                    ],                                  key='-SD-DATA-F-',      visible=False,  **F_kwds ),
                ],
                [
                    sg.Text( "Seed Raw Data: ",                                 visible=LO_REC,
                                                                                size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SD-SEED-',        visible=LO_REC,
                                                                                size=inlong,    **T_kwds ),
                ],
            ],                                          key='-SD-SEED-F-',                      **F_kwds_big ),
        ],
    ] + [

        [
            sg.Frame( SE_SEED_FRAME, [
                [
                    sg.Radio( "None",             "SE", key='-SE-NON-',         visible=LO_REC,
                                                                                default=LO_BAK, **B_kwds ),
                    sg.Radio( "Hex",              "SE", key='-SE-HEX-',         visible=LO_PRO, **B_kwds ),
                    sg.Radio( "Die rolls, ... (SHA-512)", "SE", key='-SE-SHA-', visible=LO_REC,
                                                                                default=LO_CRE or LO_PRO, **B_kwds ),
                    sg.Checkbox( 'Ignore Bad Entropy', key='-SE-SIGS-C-',       visible=LO_REC or LO_PRO,
                                                                                disabled=False, **T_hue( B_kwds, 3/20 )),
                ],
                [
                    sg.Column( [
                        [
                            sg.Text( "Die rolls, etc.:",key='-SE-DATA-T-',      size=prefix,    **T_kwds ),
                            sg.Input( "",               key='-SE-DATA-',        size=inlong,    **I_kwds ),
                        ],
                    ],                                  key='-SE-DATA-F-',      visible=False ),
                ],
                [
                    sg.Text( "Seed XOR Data: ",                                 visible=LO_REC,
                                                                                size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SE-SEED-',        visible=LO_REC,
                                                                                size=inlong,    **T_kwds ),
                ],
            ],                                          key='-SE-SEED-F-',      visible=LO_CRE, **F_kwds_big ),
        ]
    ] + [
        [
            sg.Frame( SS_SEED_FRAME, [
                [
                    sg.Text( "Seed Secret: ",                                   size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SEED-',           size=inlong,    **T_kwds ),
                ],
                [
                    sg.Checkbox( "Using BIP-39:",       key='-AS-BIP-CB-',      visible=LO_CRE,
                                                                                default=True,
                                                                                size=prefix,    **T_hue( B_kwds, -1/20 )),
                    sg.Text( '',                        key='-AS-BIP-',         visible=LO_CRE, **T_hue( T_kwds_dense, -1/20 )),
                ],
                [
                    sg.Column( [
                        [
                            sg.Frame( "BIP-39 Passphrase", [
                                [
                                    sg.Text( "Passphrase (encrypt):",                           **T_kwds ),
                                    sg.Input( f"{passphrase or ''}",
                                                        key='-PASSPHRASE-',     size=inputs,    **I_kwds ),
                                ],
                            ],                          key='-PASSPHRASE-F-',   visible=True,   **F_kwds ),
                        ],
                        [
                            sg.Text( "Recovery needs: ",                        size=prefix,    **T_kwds ),
                            sg.Input( f"{group_threshold}", key='-THRESHOLD-',  size=tiny,      **I_kwds ),
                            sg.Text( f"of {len(groups)}", key='-RECOVERY-',                     **T_kwds ),
                            sg.Button( '+', **B_kwds ),
                            sg.Text( "Mnemonic Card Groups",                                    **T_kwds ),
                        ],
                        group_body,
                    ] ),
                    sg.Multiline( "",                   key='-INSTRUCTIONS-',   size=(80,15),
                                  no_scrollbar=True, horizontal_scroll=LO_PRO or LO_REC,        **T_kwds_dense ),
                ],
            ],                                          key='-GROUPS-F-',                       **F_kwds_big ),
        ],
    ] + [
        [
            sg.Frame( 'Cryptocurrencies and Paper Wallets', [
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
            ],                                          key='-WALLET-F-',       visible=LO_CRE and wallet_pwd is not False,
                                                                                                **F_kwds_big ),  # noqa: E126
        ],
    ] + [
        [
            sg.Frame( f"Your SLIP-39 Recovery Groups ({'Print directly, or ' if printers is not None else ''}Save to removable USB)!", [
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
            ],                                          key='-SUMMARY-F-',                      **F_kwds_big ),
        ],
    ] + [
        [
            sg.Frame( 'Status; Wallets derived from Seed, or any problems we detect.', [
                [
                    sg.Text(                            key='-STATUS-',                         **T_kwds ),
                ]
            ],                                          key='-STATUS-F-',                       **F_kwds_big ),
        ],
    ] + [
        [
            sg.Frame( 'SLIP-39 Recovery Mnemonics on the Cards saved to PDF.', [
                [
                    sg.Multiline( "",                   key='-MNEMONICS-'+sg.WRITE_ONLY_KEY,
                                                                                size=mnemos,    **I_kwds_small )
                ]
            ],                                          key='-MNEMONICS-F-',    visible=LO_PRO, **F_kwds_big ),
        ],
    ] + [
        [
            sg.Frame( 'Seed Recovered from SLIP-39 Mnemonics', [
                [
                    sg.Text( "Seed Verified: ",                                 size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SEED-RECOVERED-', size=inlong,    **T_kwds ),
                ],
            ],                                          key='-RECOVERED-F-',    visible=LO_PRO, **F_kwds_big ),
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

    Stores the last known state of the -SD-... radio buttons, and saves/restores the user data being
    supplied on for BIP/SLIP/FIX.  If event indicates one of our radio-buttons is re-selectedd, then
    also re-generate the random data.  If a system event occurs (eg. after a Controls change),
    restores our last-known radio button and data.  Since we cannot know if/when our main window is
    going to disappear and be replaced, we constantly save the current state.

    Reports the quality of the Seed Data in the frame label.
    """
    SD_CONTROLS			= [
        '-SD-128-RND-',
        '-SD-256-RND-',
        '-SD-512-RND-',
        '-SD-BIP-',			# Recover 128- to 256-bit Mnemonic Seed Entropy
        '-SD-BIP-SEED-',		# Recover 512-bit Generated Seed w/ passphrase
        '-SD-SLIP-',
    ]
    changed			= False
    # Some system event (eg. __TIMEOUT__ immediately after a new main window is created, or due to
    # scheduled callback); restore where we left off if known, and if the remembered control is
    # visible.  This allows continuation between major screen changes w/ full controls regeneration.
    # As long as the new screen contains the current visible control, we'll continue editing our Seed
    # Data wherever we left off.  If the new screen has different controls, we'll get whatever is
    # there, instead.
    if not event.startswith( '-' ):
        log.warning( f"Restoring Seed Source w/ event {event} from saved {update_seed_data.src}"
                     f" data/password{' (none saved)' if update_seed_data.src not in update_seed_data.was else ''}" )
        if not values[update_seed_data.src]:
            # Something else has been selected (probably due to a major display change).
            if window[update_seed_data.src].visible:
                # And its still visible; switch back to where we were...
                for src in SD_CONTROLS:
                    values[src]	= False
                values[update_seed_data.src] = True
                window[update_seed_data.src].update( True )
            else:
                # And it isn't available; switch to newly available default...
                update_seed_data.src, = ( src for src in SD_CONTROLS if values[src] )
            changed		= True  # and force controls visiblity update
        data, pswd, seed	= update_seed_data.was.get( update_seed_data.src, ('', '', None) )
    elif not values[update_seed_data.src]:
        # A controls selection change.
        update_seed_data.src,	= ( src for src in SD_CONTROLS if values[src] )
        changed			= True  # and force controls visiblity update
        data, pswd, seed	= update_seed_data.was.get( update_seed_data.src, ('', '', None) )
    else:
        # A normal user-initiated window event, w/ no controls change; get updated value/window data
        if event == update_seed_data.src:
            # Same radio-button re-selected; just force an update (eg. re-generate random)
            log.info( f"Seed Data update forced due to event: {event!r}" )
            changed		= True  # and force controls visiblity update
        data, pswd, seed	= values['-SD-DATA-'], values['-SD-PASS-'], window['-SD-SEED-'].get()

    # Now that we've recovered which Seed Data control was previously in play (and any data/pswd),
    # update window/value content and other controls' visibility for this -SD-...  selection; but
    # only IF the data has changed.  Otherwise, cursor motion in input fields will be foiled...
    if window['-SD-DATA-'].get() != data:
        log.info( f"Updating -SD-DATA- from {window['-SD-DATA-'].get()} to {data}" )
        window['-SD-DATA-'].update( data )
    values['-SD-DATA-']		= data
    if window['-SD-PASS-'].get() != pswd:
        window['-SD-PASS-'].update( pswd )
    if 'FIX' in update_seed_data.src:
        window['-SD-DATA-F-'].update( "Hex data: " )
        window['-SD-DATA-F-'].update( visible=True  )
        window['-SD-PASS-C-'].update( visible=False )
        window['-SD-PASS-F-'].update( visible=False )
    elif 'BIP-SEED' in update_seed_data.src:
        # We're recovering the (decrypted) BIP-39 Seed, so we require the Passphrase!
        window['-SD-DATA-F-'].update( "BIP-39 Mnemonic (for 512-bit Seed Recovery): " )
        window['-SD-DATA-F-'].update( visible=True )
        window['-SD-PASS-C-'].update( visible=True )
        window['-SD-PASS-F-'].update(
            "BIP-39 passphrase (won't be needed for Recovery)",
            visible=values['-SD-PASS-C-']
        )
    elif 'BIP' in update_seed_data.src:
        # We're recovering the BIP-39 Seed Phrase *Entropy*, NOT the derived (decrypted) 512-bit
        # Seed Data!  So, we don't deal in Passphrases, here.  The Passphrase (to encrypt the Seed,
        # when "Using BIP-39") is only required to display the correct wallet addresses.
        window['-SD-DATA-F-'].update( "BIP-39 Mnemonic to Back Up: " )
        window['-SD-DATA-F-'].update( visible=True )
        window['-SD-PASS-C-'].update( visible=False )
        window['-SD-PASS-F-'].update( visible=False )
    elif 'SLIP' in update_seed_data.src:
        window['-SD-DATA-F-'].update( "SLIP-39 Mnemonics to Back Up: " )
        window['-SD-DATA-F-'].update( visible=True )
        window['-SD-PASS-C-'].update( visible=True )
        window['-SD-PASS-F-'].update(
            passphrase_trezor_incompatible,
            visible=values['-SD-PASS-C-']
        )
    elif 'RND' in update_seed_data.src:
        window['-SD-DATA-F-'].update( visible=False )
        window['-SD-PASS-C-'].update( visible=False )
        window['-SD-PASS-F-'].update( visible=False )

    # We got our working -SD-DATA- into 'data' (maybe from last time 'round), compute seed.
    status			= None
    bits			= None
    if not seed:
        seed		= '-' * ( BITS_DEFAULT // 4 )
    if 'BIP' in update_seed_data.src:
        # When recovering from BIP-39 for use in SLIP-39, we always recover the ORIGINAL 128- or
        # 256-bit Entropy used to create the BIP-39 Mnemonic (other sizes of BIP-39 Entropy are not
        # supported).  This is what we want to back up -- NOT the 512-bit Seed output from the
        # processing the BIP-39 Mnemonic + passphrase; thus, we can always re-produce the BIP-39
        # mnemonic.  Later, (when producing wallets) we'll see if the desired target device seed
        # will be transmitted via BIP-39 + passphrase, or SLIP-39, and produce the correct Seed for
        # deriving predicted wallet addresses.
        try:
            # No passphrase allowed/required, to get original BIP-39 Mnemonic Entropy Only needed
            # (later) for Account generation.  This *may* produce a number of bits NOT in
            # default.BITS!  (eg. from a 160- or 192-bit BIP-39 Mnemonics). This is allowable,
            # because if as_entropy is True, we'll be BIP-39-encrypting the Seed Data to generate a
            # 512-bit seed.
            as_entropy		= 'BIP-SEED' not in update_seed_data.src
            if as_entropy:
                if pswd:
                    log.warning( "BIP-39 Seed Passphrase (decrypt) ignored; using Seed Phrase Entropy, not decrypted Seed!" )
                passphrase	= b""
            else:
                if pswd.strip() != pswd:
                    log.warning( "BIP-39 Seed Passphrase (decrypt) contains leading/trailing whitespace; are you certain this is correct?" )
                passphrase	= pswd.encode( 'UTF-8' )
            seed		= recover_bip39(
                mnemonic	= data.strip(),
                passphrase	= passphrase,
                as_entropy	= as_entropy,
            )
            bits		= len( seed ) * 8
            assert bits in BITS_allowed( values ), \
                f"Only {commas(BITS, final='and')}-bit BIP-39 Mnemonics supported, unless 'Using BIP-39' selected"
        except Exception as exc:
            status		= f"Invalid BIP-39 recovery mnemonic: {exc}"
            log.warning( status )
    elif 'SLIP' in update_seed_data.src:
        window['-SD-PASS-F-'].update( visible=values['-SD-PASS-C-'] )
        try:
            passphrase		= pswd.strip().encode( 'UTF-8' )
            seed		= recover(
                mnemonics	= list( mnemonic_continuation( data.strip().split( '\n' ))),
                passphrase	= passphrase,
            )
            bits		= len( seed ) * 8
        except Exception as exc:
            log.warning( f"SLIP-39 recovery failed w/ {data!r}: {exc}" )
            status		= f"Invalid SLIP-39 recovery mnemonics: {exc}"
    elif 'FIX' in update_seed_data.src:
        bits			= int( update_seed_data.src.split( '-' )[2] )
        try:
            # 0-fill and truncate any supplied hex data to the desired bit length
            data_filled		= f"{data:<0{bits // 4}.{bits // 4}}"
            seed 		= codecs.decode( data_filled, 'hex_codec' )
        except Exception as exc:
            log.warning( f"Fixed hex recovery failed w/ {data!r}: {exc}" )
            status		= f"Invalid Hex for {bits}-bit fixed seed: {exc}"
    elif changed or not seed:  # RND.  Regenerated each time changed, or not valid
        bits			= int( update_seed_data.src.split( '-' )[2] )
        seed			= random_secret( bits // 8 )

    # Compute any newly computed/recovered binary Seed Data bytes as hex. Must be 128-, 256- or
    # 512-bit hex data.  Do a final comparison against current -SD-SEED- to detect changes.
    if status:
        status			= f"Invalid Seed Data: {status}"
    else:
        try:
            if type(seed) is not str:
                seed		= codecs.encode( seed, 'hex_codec' ).decode( 'ascii' )
            if bits is None:  # For previously defined seed_data, compute length
                bits		= len( seed ) * 4
            assert len( seed ) * 4 == bits, \
                f"{len(seed)*4}-bit data recovered; expected {bits} bits: {seed}"
            assert bits in BITS_allowed( values ), \
                f"Invalid {bits}-bit data size: {seed}"
        except Exception as exc:
            status			= f"Invalid Seed Data: {exc}"
    if status:
        if not bits:
            bits		= BITS_DEFAULT
        seed			= '-' * (bits // 4)
    if window['-SD-SEED-'].get() != seed:
        update_seed_data.deficiencies = ()
        changed			= True

    # Analyze the seed for Signal harmonic or Shannon entropy failures, if we're in a __TIMEOUT__
    # (between keystrokes or after a major controls change).  Otherwise, if the seed's changed,
    # request a __TIMEOUT__; when it invokes, perform the entropy analysis.
    if status is None:
        if event == '__TIMEOUT__':
            seed_bytes		= codecs.decode( seed, 'hex_codec' )
            scan_dur,(sigs,shan) = timing( scan_entropy, instrument=True )( seed_bytes, show_details=True )  # could be (None,None)
            sigs_rate		= f"{rate_dB( max( sigs ).dB if sigs else None, what='Harmonics')}"
            shan_rate		= f"{rate_dB( max( shan ).dB if shan else None, what='Shannon Entropy')}"
            window['-SD-SEED-F-'].update( f"{SD_SEED_FRAME}; {sigs_rate}, {shan_rate}" )
            disp_dur,analysis	= timing( display_entropy, instrument=True )( sigs, shan, what=f"{len(seed_bytes)*8}-bit Seed Source" )
            update_seed_data.deficiencies = (sigs, shan)
            update_seed_data.analysis = analysis or '(No entropy analysis deficiencies found in Seed Data)'
            log.debug( f"Seed Data  Entropy Analysis took {scan_dur:.3f}s + {disp_dur:.3f}s == {scan_dur+disp_dur:.3f}s: {analysis}" )
        elif changed:
            log.info( f"Seed Data requests __TIMEOUT__ w/ current source: {update_seed_data.src!r}" )
            values['__TIMEOUT__'] = .5
    else:
        window['-SD-SEED-F-'].update( f"{SD_SEED_FRAME}; Invalid" )

    # Since a window[...].update() doesn't show up to a .get() 'til the next cycle of the display,
    # we'll communicate updates to successive functions via values.
    values['-SD-SEED-'] 	= seed
    window['-SD-SEED-'].update( seed )

    # Finally, remember what data/pswd/seed we're working on, in case we get a major controls change.
    update_seed_data.was[update_seed_data.src] = data, pswd, seed
    return status

update_seed_data.src		= '-SD-BIP-'  # noqa: E305
update_seed_data.was		= {
    '-SD-BIP-':		(BIP39_EXAMPLE_128,  "", None),
    '-SD-BIP-SEED-':	(BIP39_EXAMPLE_128,  "", None),
    '-SD-SLIP-':	(SLIP39_EXAMPLE_128, "", None),
}
update_seed_data.deficiencies	= ()
update_seed_data.analysis	= ''


def update_seed_entropy( event, window, values ):
    """Respond to changes in the extra Seed Entropy, and recover/generate the -SE-SEED-.  It is
    expected to be exactly the same size as the -SD-SEED- data.  Stores the last known state of the
    -SE-... radio buttons, updating visibilities on change.

    We analyze the entropy of the *input* data (as UTF-8), not the resultant entropy.
    """
    SE_CONTROLS			= [
        '-SE-NON-',
        '-SE-HEX-',
        '-SE-SHA-',
    ]
    data			= values['-SE-DATA-']
    try:
        data_bytes		= data.encode( 'UTF-8' )
    except Exception as exc:
        status			= f"Invalid data {data!r}: {exc}"

    for src in SE_CONTROLS:
        if values[src] and update_seed_entropy.src != src:
            # If selected radio-button for Seed Entropy source changed, save last source's working
            # data and restore what was, last time we were working on this source.
            data		= update_seed_entropy.was.get( src, '' )
            update_seed_entropy.src = src
            window['-SE-DATA-'].update( data )
            values['-SE-DATA-']	= data
            if 'NON' in update_seed_entropy.src:
                window['-SE-DATA-T-'].update( "" )
            elif 'HEX' in update_seed_entropy.src:
                window['-SE-DATA-T-'].update( "Hex digits: " )
            else:
                window['-SE-DATA-T-'].update( "Die rolls, etc.: " )

    # Evaluate the nature of the extra entropy, and place interpretation to analyze in data_bytes.
    # Binary "hex" data should be neutral harmonically and in Shannon entropy.  However, some data
    # such as dice rolls may exhibit restricted symbol values; try to deduce this case, restricting
    # Shannon Entropy 'N' to binary (coin-flip) or 4, 6 and 10-sided dice.
    status			= None
    seed			= values.get( '-SD-SEED-', window['-SD-SEED-'].get() )
    bits			= len( seed ) * 4

    strides			= 8
    overlap			= False
    ignore_dc			= True
    N				= None
    interpretation		= 'Trust but Verify ;-'
    log.debug( f"Computing Extra Entropy, for {bits}-bit Seed Data: {seed!r}" )
    if 'NON' in update_seed_entropy.src:
        window['-SE-DATA-F-'].update( visible=False )
        extra_entropy		= b''
    elif 'HEX' in update_seed_entropy.src:
        window['-SE-DATA-F-'].update( visible=True )
        try:
            # 0-fill and truncate any supplied hex data to the desired bit length, SHA-512 stretch
            extra_entropy	= stretch_seed_entropy( data, n=0, bits=bits, encoding='hex_codec' )
        except Exception as exc:
            status		= f"Invalid Hex {data!r} for {bits}-bit extra seed entropy: {exc}"
        else:
            data_bytes		= codecs.decode( f"{data:<0{bits // 4}.{bits // 4}}", 'hex_codec' )
            interpretation	= "Hexadecimal Data"
            strides		= None
            overlap		= True
            ignore_dc		= False
    else:
        window['-SE-DATA-F-'].update( visible=True )
        try:
            # SHA-512 stretch and possibly truncate supplied Entropy (show for 1st Seed)
            extra_entropy	= stretch_seed_entropy( data, n=0, bits=bits, encoding='UTF-8' )
        except Exception as exc:
            status		= f"Invalid data {data!r} for {bits}-bit extra seed entropy: {exc}"
        if data and all( '0' <= c <= '9' for c in data ):
            N			= {
                '0':  2, '1':  2,				# Coin flips
                '2':  6, '3':  6, '4':  6, '5':  6, '6':  6,    # 6-sided (regular) dice
                '7': 10, '8': 10, '9': 10, 		 	# 10-sided (enter 0 for the 10 side)
            }[max( data )]
            interpretation	= f"{N}-sided Dice" if N > 2 else "Coin-flips/Binary"

    # Compute the Seed Entropy as hex.  Will be 128-, 256- or 512-bit hex data.  Ensure
    # extra_{bytes,entropy} are bytes and ASCII (hex, or -) respectively.
    if status or not extra_entropy:
        extra_entropy		= '-' * ( bits // 4 )
        extra_bytes		= b''
    elif type( extra_entropy ) is bytes:
        extra_bytes		= extra_entropy
        extra_entropy		= codecs.encode( extra_bytes, 'hex_codec' ).decode( 'ascii' )
    else:
        extra_bytes		= codecs.decode( extra_entropy, 'hex_codec' )

    if window['-SE-SEED-'].get() != extra_entropy:
        update_seed_entropy.deficiencies = ()

    se_seed_frame		= f"{SE_SEED_FRAME} ({interpretation})"
    if status is None and len( data_bytes ) >= 8 and not update_seed_entropy.deficiencies:
        if event == '__TIMEOUT__':
            scan_dur,(sigs,shan) = timing( scan_entropy, instrument=True )(  # could be (None,None)
                data_bytes,
                strides		= strides,
                overlap		= overlap,
                ignore_dc	= ignore_dc,
                N		= N,
                signal_threshold = 300/100,
                shannon_threshold = 10/100,
                show_details	= True
            )
            sigs_rate		= f"{rate_dB( max( sigs ).dB if sigs else None, what='Harmonics')}"
            shan_rate		= f"{rate_dB( max( shan ).dB if shan else None, what='Shannon Entropy')}"
            window['-SE-SEED-F-'].update( f"{se_seed_frame}: {sigs_rate}, {shan_rate}" )
            disp_dur,analysis	= timing( display_entropy, instrument=True )( sigs, shan, what=f"{len(extra_bytes)*8}-bit Extra Seed Entropy" )
            update_seed_entropy.deficiencies = (sigs, shan)
            update_seed_entropy.analysis = analysis or '(No entropy analysis deficiencies found in Extra Seed Entropy)'
            log.debug( f"Seed Extra Entropy Analysis took {scan_dur:.3f}s + {disp_dur:.3f}s == {scan_dur+disp_dur:.3f}s: {analysis}" )
        else:
            log.info( f"Seed Extra requests __TIMEOUT__ w/ current source: {update_seed_entropy.src!r}" )
            values['__TIMEOUT__'] = .5
    elif status:
        window['-SE-SEED-F-'].update( f"{se_seed_frame}: Invalid" )
        update_seed_entropy.analysis = f"{se_seed_frame}: {status}"
    elif len( data_bytes ) < 8:
        window['-SE-SEED-F-'].update( f"{se_seed_frame}" )
        update_seed_entropy.analysis = f"{se_seed_frame}: {'None Provided' if values['-SE-NON-'] else 'Insufficient for analysis'}"

    values['-SE-SEED-']		= extra_entropy
    window['-SE-SEED-'].update( extra_entropy )

    update_seed_entropy.was[update_seed_entropy.src] = data
    return status

update_seed_entropy.src	= '-SE-NON-'  # noqa: E305
update_seed_entropy.was = {}
update_seed_entropy.deficiencies = ()
update_seed_entropy.analysis = ''


def using_BIP39( values ):
    return values['-AS-BIP-CB-']


def BITS_allowed( values ):
    return BITS_BIP39 if using_BIP39( values ) else BITS


def compute_master_secret( window, values, n=0 ):
    """Validate the Seed Data and Seed Entropy, and compute the n'th master secret seed.  This is a
    simple XOR of the Seed Data, and any extra Seed Entropy -- so that the user can VISUALLY OBSERVE
    that the purported Seed Data and their provided extra Seed Entropy leads to the final master
    secret seed.  We are resilient to '-' in incoming seed_data (eg. from an incomplete BIP/SLIP-39
    recovery)

    This is a critical feature -- without this visual confirmation, it is NOT POSSIBLE to trust any
    cryptocurrency seed generation algorithm!

    This function must have knowledge of the extra Seed Entropy settings, so it inspects the
    -SE-{NON/HEX}- checkbox values.
    """
    seed_data_hex		= values.get( '-SD-SEED-', window['-SD-SEED-'].get() )
    bits			= len( seed_data_hex ) * 4
    assert bits in BITS_allowed( values ), \
        f"Invalid {bits}-bit Seed size: {seed_data_hex}"
    try:
        seed_data		= codecs.decode( seed_data_hex.replace( '-', '0' ), 'hex_codec' )
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

    There must always be a SLIP-39 passphrase; it may be empty (b'').  When using BIP-39, do would
    generally *not* supply a SLIP-39 passphrase.

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

    # Ensure that our recovered Seed (if any) matches the computed Seed!  This is ignored
    # when run without any details (ie. to clear any displayed -MNEMONICS-).
    if recohex and window['-SEED-'].get() != recohex:
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
        scutil = parse_scutil( subproc.stdout )
        if uid := scutil.get( 'UID' ):
            for session in scutil.get( 'SessionInfo', {} ).values():
                if session.get( 'kCGSSessionUserIDKey' ) == uid:
                    # eg.: "      kCGSessionLongUserNameKey : Perry Kundert"
                    full_name = session.get( 'kCGSessionLongUserNameKey' )
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
    controls			= LAYOUT_BAK,   # What level of controls complexity is desired?
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

    sg.CURRENT_LOOK_AND_FEEL	= sg.theme( THEME )  # Why?  This module global should have updated...

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
    timeout			= 0		# First time thru; refresh immediately; functions req. refresh may adjust via values['__TIMEOUT__']
    instructions		= ''		# The last instructions .txt payload found
    instructions_kwds		= dict()        # .. and its colors
    values			= dict()
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
                passphrase	= passphrase.decode( 'UTF-8' ) if passphrase else None,
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
            values['__TIMEOUT__'] = 0 		# First time through w/ new window, refresh immediately

        # Block (except for first loop, or if someone requested a __TIMEOUT__) and obtain current
        # event and input values. Until we get a new event, retain the current status
        timeout			= values.get( '__TIMEOUT__', None )  # Subsequently, default; block indefinitely (functions may adjust...)
        if timeout:
            logging.debug( f"A __TIMEOUT__ was requested: {timeout!r}" )
        event, values		= window.read( timeout=timeout )
        logging.debug( f"{event}, {pretty(values, compact=True)}" )
        if not values or event in events_termination or event in events_ignored:
            continue

        # If an event is reported, but there is no change to the data, this probably indicates a
        # cursor movement event;
        if event and event.startswith( '-' ):
            value		= values.get( event )
            if value and value == window[event]:
                logging.debug( "Cursor movement on {event}..." )
                continue

        status			= None
        status_error		= True

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
        status_se		= update_seed_entropy( event, window, values )
        status_ms		= None
        try:
            master_secret	= compute_master_secret( window, values, n=0 )
        except Exception as exc:
            status_ms		= f"Error computing master_secret: {exc}"
            logging.exception( f"{status}" )
            master_secret	= '-' * len( values['-SD-SEED-'] )
        if type(master_secret) is bytes:
            master_secret	= codecs.encode( master_secret, 'hex_codec' ).decode( 'ascii' )

        # We've now calculated any supplied Seed Data or Seed Extra Randomness (and detected any
        # Entropy Analysis deficiencies, which may be included in some instruction formats); see if
        # there are any instructional 'SLIP-39-<event>.txt' for the last event.  If so, load it into
        # the '-INSTRUCTIONS-' Multiline.  We'll split each event on its component '-', and look for
        # eg. SLIP-39-LO.txt, when we see event == '-LO-1-'.  We'll select the most specific
        # instructional .txt we can load.  Only if the current instructions is empty will we go all
        # the way back to load the generic SLIP-39.txt.  If the event corresponds to an object with
        # text/backround_color, use it in the instructional text.
        txt_segs		= ( event or '' ).strip( '-' ).split( '-' )
        instructions_path	= ''
        for txt_i in range( len( txt_segs ), 0 if instructions else -1, -1 ):
            txt_name		= '-'.join( [ 'SLIP', '39' ] + txt_segs[:txt_i] ) + '.txt'
            txt_path		= os.path.join( os.path.dirname( __file__ ), txt_name )
            try:
                with open( txt_path, 'r', encoding='UTF-8' ) as txt_f:
                    txt		= txt_f.read()
                    if txt:
                        instructions = txt
                        instructions_path = txt_path
                        break
            except FileNotFoundError:
                pass

        # If there are {...} entries in the loaded text, we'll assume they are formatting options.
        # These files form part of the program, and therefore can know about the names of internal
        # variables.  If someone can exploit these .txt files, they can just as easily exploit the
        # Python code of the program...  Let's provide access to an aggregate summary of the Entropy
        # Analysis of the Seed Data and Seed Extra Randomness, here.  If we have some poor Seed
        # Data, but provide good Seed Extra Randomness, or provide a BIP/SLIP-39 passphrase, then
        # we'll let that go.  In other words, poor Seed Data with a Passphrase is considered more
        # secure (still not recommended).  But, really bad Seed Data entropy can still overwhelm it.
        def deficiency( *deficiencies ):
            """Entropy analysis deficiencies may consists of eg. (,), (None,[]) or ([],[]).  Yields
            the largest (first item) from each, if any.  Convert to a deficiency sequence.

            """
            for alist in deficiencies:
                if alist:
                    yield alist[0]
        dB_defic		= []
        sd_defic		= list( deficiency( *update_seed_data.deficiencies ))
        if sd_defic:
            # There is a Seed Data entropy deficit!
            dB_defic.append( max( sd_defic ).dB )
        if 'NON' not in update_seed_entropy.src:
            # There is Seed Extra Randomness; is it also in entropy deficit?
            se_defic		= list( deficiency( *update_seed_entropy.deficiencies ))
            if dB_defic or se_defic:
                # Some good Seed Extra Randomness dilutes poor Seed Data entropy deficit...
                dB_defic.append( max( se_defic ).dB if se_defic else -1.0 )
        if dB_defic and window['-PASSPHRASE-'].get():
            # There's a deficit, but they're using an encryption Passphrase...
            dB_defic.append( -1.0 )
        # If None, "excellent", otherwise rating is avg of worst of Seed Data / Extra Entropy, net a
        # reduction for passphrase and good Extra Entropy.  If entropy_dB is None (excellent), or <
        # 0.0dB (ok), this is considered acceptable.
        entropy_dB		= avg( dB_defic ) if dB_defic else None
        entropy_rating		= rate_dB( entropy_dB )
        ( log.warning if dB_defic else log.info )( f"Overall entropy deficiency: {entropy_rating}, from: {commas(dB_defic)}" )

        window['-GROUPS-F-'].update( f"{SS_SEED_FRAME}: Overall entropy deficiency: {entropy_rating}" )
        instructions_fmtd	= instructions
        if '{' in instructions:
            try:
                kwds		= globals()
                kwds.update( locals() )
                instructions_fmtd = instructions.format( **kwds )
            except KeyError as exc:
                log.warning( f"Failed to format instructions {instructions_path}: Local variable {exc} not found." )

        if event.startswith( '-' ):  # One of our events (ie. not __TIMEOUT__, etc.)...
            try:
                event_element	= window.find_element( event, silent_on_error=True )
                instructions_kwds.update(
                    text_color	= event_element.TextColor,
                    background_color= event_element.BackgroundColor,
                )
            except Exception as exc:
                log.debug( f"Couldn't update instructions text color: {exc}" )
                pass
        window['-INSTRUCTIONS-'].update( instructions_fmtd, **instructions_kwds )

        # See if we should display/use the BIP-39 version of the Master Secret Seed.  Also, re-labels
        # the -PASSPHRASE-... between SLIP-39 and BIP-39.  We only support one Passphrase, even if
        # SLIP-39 is encoding the entropy in a BIP-39 Mnemonic; If BIP-39 is selected, the
        # Passphrase is assumed to be encrypting the BIP-39 Mnemonic to generate the Seed; the same
        # Passphrase must be entered on the hardware wallet along with the Mnemonic.
        using_bip39		= using_BIP39( values )  # Also triggers BIP-39 Seed generation, below

        # From this point forward, detect if we have seen any change in the computed Master Seed, or
        # in the SLIP-39 groups recovered; avoid unnecessary update of the SLIP-39 Mnemonics.  And,
        # if any status was reported in the computation of Seed Data, extra Seed Entropy or Master
        # Secret, report it now.  We'll also force this if someone clicks "Using BIP-39".  Remember
        # -- the BIP-39 Mnemonic encodes only the original Seed Entropy, so there is no concept of a
        # Passphrase.  Later, when we use the Entropy to produce wallets -- if "Using BIP-39" is
        # selected, each successive master_secret_n produces a different BIP-39 Mnemonic, and the
        # actual Seed is generated also using the specified Passphrase.
        if master_secret != master_secret_was or event == '-AS-BIP-CB-':
            log.info( "Updating SLIP-39 due to changing Master Seed" )
            window['-SEED-'].update( master_secret )
            try:
                bip39		= produce_bip39(
                    entropy	= codecs.decode( master_secret, 'hex_codec' ),
                    strength	= len( master_secret ) * 4,
                )
                window['-AS-BIP-'].update( bip39 )
            except Exception as exc:
                # Incompatible 512-bit master_secret; Disable BIP-39 representation
                log.warning( f"Error computing BIP-39: {exc}" )
                using_bip39	= False
                window['-AS-BIP-CB-'].update( False )
                values['-AS-BIP-CB-']	= False
                window['-AS-BIP-CB-'].update( disabled=True )
                window['-AS-BIP-'].update( '' )
            else:
                # The seed is BIP-39 compatible; give the option to indicating they're using BIP-39
                window['-AS-BIP-CB-'].update( disabled=False )
            details		= None

        # Recover any passphrase, discarding any details on change.  The empty passphrase b'' is the
        # default for both SLIP-39 and BIP-39.
        if window['-AS-BIP-CB-'].visible:
            # Only if the checkbox is visible in this mode, also make the BIP-39 rendering visible
            window['-AS-BIP-'].update( visible=values['-AS-BIP-CB-'] )
        window['-PASSPHRASE-F-'].update(
            'BIP-39 Passphrase' if using_bip39 else passphrase_trezor_incompatible )
        passphrase_now		= values['-PASSPHRASE-'].strip().encode( 'UTF-8' )
        if passphrase != passphrase_now:
            passphrase		= passphrase_now
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
        cps_rec			= list( cryptopaths_parser( cryptocurrency=cs_rec, edit=edit ))
        if cs_rec != cryptocurrency or cps_rec != cryptopaths:
            log.info( "Updating SLIP-39 due to changing Cryptocurrencies" )
            cryptocurrency	= cs_rec
            cryptopaths		= cps_rec
            details		= None

        # Produce a summary of the SLIP-39 recovery groups, including any passphrase needed for
        # decryption of the SLIP-39 seed, and how few/many cards will need to be collected to
        # recover the Seed.  If the SLIP-39 passphrase has changed, force regeneration of SLIP-39.
        # NOTE: this SLIP-39 standard passphrase is NOT Trezor-compatible; warn to use the Trezor
        # "hidden wallet" feature instead.
        summary_groups		= ', '.join( f"{n}({need}/{size})" for n,(need,size) in groups.items())
        summary			= f"Recover w/ {group_threshold} of {len(groups)} Groups: {summary_groups}"

        tot_cards		= sum( size for _,size in groups.values() )
        min_req			= sum( islice( sorted( ( need for need,_ in groups.values() ), reverse=False ), group_threshold ))
        max_req			= sum( islice( sorted( ( need for need,_ in groups.values() ), reverse=True  ), group_threshold ))
        summary		       += f" (from {min_req}-{max_req} of {tot_cards} cards)"
        if passphrase:
            summary	       += f", w/ {'BIP-39' if using_bip39 else 'SLIP-39'} password: {passphrase.decode( 'UTF-8' )!r})"

        window['-SUMMARY-'].update( summary )

        # Re-compute the SLIP39 Seed details.  For multiple names, each subsequent slip39.create
        # uses a master_secret produced by hashing the prior master_secret entropy.  For the 1st
        # Seed, we've computed the master_secret, above.  Each master_secret_n contains the computed
        # Seed combining Seed Data and (any) Seed Entropy, stretched for the n'th Seed.  If there is
        # no extra Seed Entropy, we will fail to produce subsequent seeds.  Recompute the desired
        # cryptopaths w/ any path adjusts, in case derivation of multiple Paper Wallets is desired.
        #
        # We avoid recomputing this unless something about the seed or the recovered groups changes;
        # each time we recompute -- even without any changes -- the SLIP-39 Mnemonics will change,
        # due to the use of entropy in the SLIP-39 process.
        if not details or names[0] not in details:
            log.info( f"SLIP39 details for {names}..." )
            try:
                details		= {}
                for n,name in enumerate( names ):
                    master_secret_n	= compute_master_secret( window, values, n=n )
                    assert n > 0 or codecs.encode( master_secret_n, 'hex_codec' ).decode( 'ascii' ) == master_secret, \
                        "Computed Seed for 1st SLIP-39 Mnemonics didn't match"
                    details[name] = create(
                        name		= name,
                        group_threshold	= group_threshold,
                        groups		= groups,
                        master_secret	= master_secret_n,
                        passphrase	= passphrase,
                        using_bip39	= using_bip39,
                        cryptopaths	= cryptopaths,
                    )
            except Exception as exc:
                status		= f"Error creating: {exc}"
                logging.exception( f"{status}" )
                update_seed_recovered( window, values, None )
                details		= None
                continue

        # Display the computed SLIP-39 Mnemonics for the first name.  We know names[0] is in details...
        # If we're using BIP-39, any supplied passphrase is *not* a SLIP-39 passphrase, so don't attempt
        # to decode SLIP-39 using the passphrase.
        if status := update_seed_recovered( window, values, details[names[0]],
                                            passphrase=b'' if using_bip39 else passphrase ):
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
        if wallet_pwd is not False and values['-WALLET-PASS-'] or values['-WALLET-HINT-']:
            # And, if Paper Wallets haven't been disabled completely, remember our password/hint.
            # If we're supplied a wallet password "hint", we allow even the empty wallet password.
            wallet_pwd		= values['-WALLET-PASS-']
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
                # A bad Entropy Analysis results in a watermark, warning that the SLIP-39 Mnemonic Seed may
                # be insecure.
            if entropy_dB is None or entropy_dB < 0:
                watermark	= None
            else:
                watermark	= f"Seed Entropy: {entropy_rating_dB( entropy_dB )}"
            try:
                card_format	= next( c for c in CARD_SIZES if values[f"-CS-{c}-"] )
                paper_format	= next( pf for pn,pf in PAPER_FORMATS.items() if values[f"-PF-{pn}-"] )
                wallet_format	= next( (f for f in WALLET_SIZES if values.get( f"-WALLET-SIZE-{f}-" )), None )
                double_sided	= values['-PF-DOUBLE-']
                details		= write_pdfs(
                    names		= details,
                    using_bip39		= using_bip39,
                    card_format		= card_format,
                    paper_format	= paper_format,
                    cryptocurrency	= cryptocurrency,
                    edit		= edit,
                    wallet_pwd		= wallet_pwd,
                    wallet_pwd_hint	= wallet_pwd_hint,
                    wallet_format	= wallet_format,
                    filepath		= filepath,
                    printer		= printer,
                    watermark		= watermark,
                    double_sided	= double_sided,
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
