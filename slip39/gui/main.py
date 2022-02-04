import argparse
import codecs
import hashlib
import logging
import math
import os

import PySimpleGUI as sg

from ..types		import Account
from ..api		import create, group_parser, random_secret
from ..recovery		import recover, recover_bip39
from ..util		import log_level, log_cfg
from ..layout		import write_pdfs
from ..defaults		import GROUPS, GROUP_THRESHOLD_RATIO, CRYPTO_PATHS, CARD, CARD_SIZES

log				= logging.getLogger( __package__ )

font				= ('Courier', 14)
font_small			= ('Courier', 11)

I_kwds				= dict(
    change_submits	= True,
    font		= font,
)
T_kwds				= dict(
    font		= font,
)
F_kwds				= dict(
    font		= font,
)
B_kwds				= dict(
    font		= font,
    enable_events	= True,
)


def groups_layout( names, group_threshold, groups, passphrase=None ):
    """Return a layout for the specified number of SLIP-39 groups.

    """

    group_body			= [
        sg.Frame(
            '#', [[ sg.Column( [
                [ sg.Text( f'{g+1}', **T_kwds ) ]
                for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
            ], key='-GROUP-NUMBER-' ) ]], **F_kwds
        ),
        sg.Frame(
            'Recovery Group', [[ sg.Column( [
                [ sg.Input( f'{g_name}', key=f'-G-NAME-{g}', **I_kwds ) ]
                for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
            ], key='-GROUP-NAMES-' ) ]], **F_kwds
        ),
        sg.Frame(
            'Needs at least', [[ sg.Column( [
                [ sg.Input( f'{g_need}', key=f'-G-NEED-{g}', **I_kwds ) ]
                for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
            ], key='-GROUP-NEEDS-' ) ]], **F_kwds
        ),
        sg.Frame(
            'of Cards in Group', [[ sg.Column( [
                [ sg.Input( f'{g_size}', key=f'-G-SIZE-{g}', **I_kwds ) ]
                for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
            ], key='-GROUP-SIZES-' ) ]], **F_kwds
        ),
    ]
    prefix			= (32, 1)
    inputs			= (32, 1)
    layout                      = [
        [
            sg.Frame( 'Output PDF File(s)', [
                [
                    sg.Text( "Save PDF(s) to (ie. USB drive): ",                size=prefix,    **T_kwds ),
                    sg.Input( sg.user_settings_get_entry( "-target folder-", ""),
                                                        key='-TARGET-',         size=inputs,    **I_kwds ),  # noqa: E127
                    sg.FolderBrowse( **B_kwds ),
                ],
                [
                    sg.Text( "Seed Name(s): ",                                  size=prefix,    **T_kwds ),
                    sg.Input( f"{', '.join( names )}",  key='-NAMES-',          size=inputs,    **I_kwds ),
                    sg.Text( "(default is 'SLIP39...'; comma-separated)",                       **T_kwds ),
                ],
                [
                    sg.Text( "Card size: ",                                     size=prefix,    **T_kwds ),
                ] + [
                    sg.Radio( f"{card}", "CS",          key=f"-CS-{card}", default=(card == CARD), **B_kwds )
                    for card in CARD_SIZES
                ],
            ],                                                  key='-OUTPUT-F-',               **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( 'Seed Data Source (256-bit seeds produce more Mnemonic words to type into your Trezor; 512-bit seeds aren\'t Trezor compatible)', [
                [
                    sg.Radio( "128-bit Random", "SD",   key='-SD-128-RND-',     default=True,   **B_kwds ),
                    sg.Radio( "256-bit Random", "SD",   key='-SD-256-RND-',     default=False,  **B_kwds ),
                    sg.Radio( "512-bit Random", "SD",   key='-SD-512-RND-',     default=False,  **B_kwds ),
                ],
                [
                    sg.Radio( "128-bit Fixed ", "SD",   key='-SD-128-FIX-',     default=False,  **B_kwds ),
                    sg.Radio( "256-bit Fixed ", "SD",   key='-SD-256-FIX-',     default=False,  **B_kwds ),
                    sg.Radio( "512-bit Fixed ", "SD",   key='-SD-512-FIX-',     default=False,  **B_kwds ),
                ],
                [
                    sg.Radio( "512-bit BIP-39", "SD",   key='-SD-BIP-',         default=False,  **B_kwds ),
                    sg.Radio( "SLIP-39",        "SD",   key='-SD-SLIP-',        default=False,  **B_kwds ),
                ],
                [
                    sg.Frame( 'From', [
                        [
                            sg.Text( "Mnemonic(s): ",   key='-SD-DATA-T-',      size=prefix,    **T_kwds ),
                            sg.Multiline( "",           key='-SD-DATA-',        size=(128,1),   **I_kwds ),
                        ],
                    ],                                  key='-SD-DATA-F-',      visible=False,  **F_kwds ),
                ],
                [
                    sg.Frame( 'Passphrase (if provided when Mnemonic was created)', [
                        [
                            sg.Text( "Passphrase (decrypt): ",                  size=prefix,    **T_kwds ),
                            sg.Input( "",               key='-SD-PASS-',        size=inputs,    **I_kwds ),
                        ],
                    ],                                  key='-SD-PASS-F-',      visible=False,  **F_kwds ),
                ],
                [
                    sg.Text( "Seed Data: ",                                     size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SD-SEED-',        size=(128,1),   **T_kwds ),
                ],
            ],                                          key='-SD-SEED-F-',                      **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( '⊻ XOR Extra Seed Entropy (eg. Die rolls, ...)', [
                [
                    sg.Radio( "Hex",              "SE", key='-SE-HEX-',         default=True,   **B_kwds ),
                    sg.Radio( "SHA-512 Stretched","SE", key='-SE-SHA-',         default=False,  **B_kwds ),
                ],
                [
                    sg.Text( "Entropy (Hex): ",         key='-SE-DATA-T-',      size=prefix,    **T_kwds ),
                    sg.Input( "",                       key='-SE-DATA-',        size=(128,1),   **I_kwds ),
                ],
                [
                    sg.Text( "Seed Entropy: ",                                  size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SE-SEED-',        size=(128,1),   **T_kwds ),
                ],
            ],                                          key='-SE-SEED-F-',                      **F_kwds ),
        ]
    ] + [
        [
            sg.Frame( 'Master Secret', [
                [
                    sg.Text( "Seed: ",                                          size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SEED-',           size=(128,1),   **T_kwds ),
                ],
            ],                                          key='-SEED-F-',                         **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( 'Groups', [
                [
                    sg.Column( [
                        [
                            sg.Text( "Requires recovery of at least: ",         size=prefix,    **T_kwds ),
                            sg.Input( f"{group_threshold}", key='-THRESHOLD-',  size=inputs,    **I_kwds ),
                            sg.Text( f"(of {len(groups)} SLIP-39 Recovery Groups)",
                                                        key='-RECOVERY-',                       **T_kwds ),  # noqa: E127
                        ],
                        [
                            sg.Text( "Passphrase (encrypt): ",                  size=prefix,    **T_kwds ),
                            sg.Input( f"{passphrase or ''}",
                                                        key='-PASSPHRASE-',     size=inputs,    **I_kwds ),  # noqa: E127
                            sg.Text( "(NOT Trezor compatible, and must be saved separately!!)", **T_kwds ),
                        ],
                        [
                            sg.Button( '+', **B_kwds ),
                        ],
                        group_body,
                    ] ),
                ],
            ],                                          key='-GROUPS-F-',                       **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( 'Summary', [
                [
                    sg.Text(                            key='-SUMMARY-',                        **T_kwds ),
                ]
            ],                                          key='-SUMMARY-F-',                      **F_kwds ),
        ],
        [
            sg.Button( 'Save', **B_kwds ), sg.Button( 'Exit', **B_kwds ),
        ],
        [
            sg.Frame( 'Status', [
                [
                    sg.Text(                            key='-STATUS-',                         **T_kwds ),
                ]
            ],                                          key='-STATUS-F-',                       **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( 'SLIP39 Mnemonics Output', [
                [
                    sg.Multiline( "",                   key='-MNEMONICS-',      size=(190,10),   font=font_small )
                ]
            ], **F_kwds ),
        ],
    ] + [
        [
            sg.Frame( 'Seed Recovery from SLIP39 Mnemonics', [
                [
                    sg.Text( "Seed Verified: ",                                 size=prefix,    **T_kwds ),
                    sg.Text( "",                        key='-SEED-RECOVERED-', size=(128,1),   **T_kwds ),
                ],
            ],                                          key='-RECOVERED-F-',                    **F_kwds ),
        ],
    ]
    return layout


def update_seed_data( window, values ):
    """Respond to changes in the desired Seed Data source, and recover/generate and update the
    -SD-SEED-.  Stores the last known state of the -SD-... radio buttons, and saves/restores the
    user data being supplied on for BIP/SLIP/FIX.

    """
    changed			= False
    dat,pwd			= values['-SD-DATA-'],values['-SD-PASS-']
    try:
        master_secret		= codecs.decode( values['-SD-SEED-'], 'hex_codec' )
    except Exception:
        master_secret		= b''
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
            master_secret	= b''
            window['-SD-DATA-'].update( dat )
            window['-SD-PASS-'].update( pwd )
            # And change visibility of Seed Data source controls
            if 'FIX' in update_seed_data.src:
                window['-SD-DATA-T-'].update( "Hex data: " )
                window['-SD-DATA-F-'].update( visible=True  )
                window['-SD-PASS-F-'].update( visible=False )
            elif 'BIP' in update_seed_data.src:
                window['-SD-DATA-T-'].update( "BIP-39 Mnemonic: " )
                window['-SD-DATA-F-'].update( visible=True )
                window['-SD-PASS-F-'].update( visible=True )
            elif 'SLIP' in update_seed_data.src:
                window['-SD-DATA-T-'].update( "SLIP-39 Mnemonics: " )
                window['-SD-DATA-F-'].update( visible=True )
                window['-SD-PASS-F-'].update( visible=True )
            elif 'RND' in update_seed_data.src:
                window['-SD-DATA-F-'].update( visible=False )
                window['-SD-PASS-F-'].update( visible=False )

    # Now that we got our working -SD-DATA- (maybe from last time 'round), compute seed
    if 'BIP' in update_seed_data.src:
        try:
            master_secret	= recover_bip39(
                mnemonic	= dat.strip(),
                passphrase	= pwd.strip().encode( 'UTF-8' )
            )
        except Exception as exc:
            log.exception( f"BIP-39 recovery failed w/ {dat!r} ({pwd!r}): {exc}" )
            return f"Invalid BIP-39 recovery mnemonic: {exc}"
    elif 'SLIP' in update_seed_data.src:
        try:
            master_secret	= recover(
                mnemonics	= dat.strip().split( '\n' ),
                passphrase	= pwd.strip().encode( 'UTF-8' )
            )
        except Exception as exc:
            log.exception( f"SLIP-39 recovery failed w/ {dat!r} ({pwd!r}): {exc}" )
            return f"Invalid SLIP-39 recovery mnemonics: {exc}"
    elif 'FIX' in update_seed_data.src:
        bits			= int( update_seed_data.src.split( '-' )[2] )
        try:
            # 0-fill and truncate any supplied hex data to the desired bit length
            data		= f"{dat:<0{bits//4}.{bits//4}}"
            master_secret 	= codecs.decode( data, 'hex_codec' )
        except Exception as exc:
            return f"Invalid Hex for {bits}-bit fixed seed: {exc}"
    elif changed or not master_secret:  # Random.  Regenerated each time changed, or not valid
        bits			= int( update_seed_data.src.split( '-' )[2] )
        master_secret		= random_secret( bits // 8 )
    # Compute the Seed Data as hex.  Will be 128-, 256- or 512-bit hex data.
    window['-SD-SEED-'].update( codecs.encode( master_secret, 'hex_codec' ).decode( 'ascii' ))
update_seed_data.src		= None  # noqa: E305
update_seed_data.was		= {
    '-SD-BIP-': ("zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong","")  # "<mnemnonic>","<passphrase>"
}


def update_seed_entropy( window, values ):
    """Respond to changes in the extra Seed Entropy, and recover/generate the -SE-SEED-.  It is
    expected to be exactly the same size as the -SD-SEED- data.  Stores the last known state of the
    -SE-... radio buttons, updating visibilties on change.

    """
    for seed_entr_source in [
        '-SE-HEX-',
        '-SE-SHA-',
    ]:
        if values.get( seed_entr_source ) and update_seed_entropy.seed_entr != seed_entr_source:
            update_seed_entropy.seed_entr = seed_entr_source
            # Changed Seed Entropy source!
            if 'HEX' in update_seed_entropy.seed_entr:
                window['-SE-DATA-T-'].update( "Entropy (Hex): " )
            else:
                window['-SE-DATA-T-'].update( "Entropy (Die rolls, etc.): " )

    bits			= len( window['-SD-SEED-'].get() ) * 4
    if 'HEX' in update_seed_entropy.seed_entr:
        try:
            # 0-fill and truncate any supplied hex data to the desired bit length
            data		= f"{values['-SE-DATA-']:<0{bits//4}.{bits//4}}"
            master_entropy	= codecs.decode( data, 'hex_codec' )
        except Exception as exc:
            return f"Invalid Hex for {bits}-bit extra seed entropy: {exc}"
    else:
        try:
            # SHA-512 stretch and possibly truncate
            stretch		= hashlib.sha512()
            stretch.update( values['-SE-DATA-'].encode( 'UTF-8' ))
            master_entropy	= stretch.digest()[:bits//8]
        except Exception as exc:
            return f"Invalid data for {bits}-bit extra seed entropy: {exc}"

    # Compute the Seed Entropy as hex.  Will be 128-, 256- or 512-bit hex data.
    window['-SE-SEED-'].update( codecs.encode( master_entropy, 'hex_codec' ).decode( 'ascii' ))
update_seed_entropy.seed_entr	= None  # noqa: E305


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
            mset		= mnem.split()
            while mrow := mset[:20]:
                mset		= mset[20:]
                rows.append( f"{g:<8.8}" + f"{i:2} " + ' '.join( f"{m:<8}" for m in mrow ))
                g		= ''
                i		= ''

    window['-MNEMONICS-'].update( '\n'.join( rows ))

    recohex			= ''
    if mnemonics:
        reco			= recover( mnemonics, passphrase=passphrase or b'' )
        recohex			= codecs.encode( reco, 'hex_codec' ).decode( 'ascii' )
    window['-SEED-RECOVERED-'].update( recohex )


def app(
    names			= None,
    group			= None,
    threshold			= None,
    cryptocurrency		= None,
    passphrase			= None,
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

    cryptopaths			= []
    for crypto in cryptocurrency or CRYPTO_PATHS:
        try:
            if isinstance( crypto, str ):
                crypto,paths	= crypto.split( ':' )   # Find the  <crypto>,<path> tuple
            else:
                crypto,paths	= crypto		# Already a <crypto>,<path> tuple?
        except ValueError:
            crypto,paths	= crypto,None
        cryptopaths.append( (crypto,paths) )

    sg.theme( 'DarkAmber' )

    sg.user_settings_set_entry( '-target folder-', os.getcwd() )

    layout			= groups_layout( names, group_threshold, groups, passphrase )
    window			= None
    status			= None
    event			= False
    events_termination		= (sg.WIN_CLOSED, 'Exit',)
    master_secret		= None		# default to produce randomly
    while event not in events_termination:
        # Create window (for initial window.read()), or update status
        if window:
            window['-STATUS-'].update( status or 'OK' )
            window['-RECOVERY-'].update( f"(of {len(groups)} SLIP-39 Recovery Groups)", **T_kwds ),
            window['-SD-SEED-F-'].expand( expand_x=True )
            window['-SE-SEED-F-'].expand( expand_x=True )
            window['-SEED-F-'].expand( expand_x=True )
            window['-OUTPUT-F-'].expand( expand_x=True )
            window['-SUMMARY-F-'].expand( expand_x=True )
            window['-STATUS-F-'].expand( expand_x=True )
            window['-RECOVERED-F-'].expand( expand_x=True )
            window['-GROUPS-F-'].expand( expand_x=True )
            timeout		= None 		# Subsequently, block indefinitely
        else:
            window		= sg.Window( f"{', '.join( names or [ 'SLIP39' ] )} Mnemonic Cards", layout )
            timeout		= 0 		# First time through, refresh immediately

        status			= None
        event, values		= window.read( timeout=timeout )
        logging.info( f"{event}, {values}" )
        if not values or event in events_termination:
            continue

        if event == '+' and len( groups ) < 16:
            # Add a SLIP39 Groups row (if not already at limit)
            g			= len( groups )
            name		= f"Group{g+1}"
            needs		= (2,3)
            groups[name] 	= needs
            values[f"-G-NAME-{g}"] = name
            values[f"-G-NEED-{g}"] = needs[0]
            values[f"-G-SIZE-{g}"] = needs[1]
            window.extend_layout( window['-GROUP-NUMBER-'], [[ sg.Text(  f"{g+1}",                          **T_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-NAMES-'],  [[ sg.Input( f"{name}",     key=f"-G-NAME-{g}", **I_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-NEEDS-'],  [[ sg.Input( f"{needs[0]}", key=f"-G-NEED-{g}", **I_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-SIZES-'],  [[ sg.Input( f"{needs[1]}", key=f"-G-SIZE-{g}", **I_kwds ) ]] )  # noqa: 241

        if status := update_seed_data( window, values ):
            update_seed_recovered( window, values, None )
            continue
        if status := update_seed_entropy( window, values ):
            update_seed_recovered( window, values, None )
            continue

        # Compute the Master Secret Seed, from the supplied Seed Data and any extra Seed Entropy
        data			= codecs.decode( window['-SD-SEED-'].get(), 'hex_codec' )
        entr			= codecs.decode( window['-SE-SEED-'].get(), 'hex_codec' )
        seed			= bytes( d ^ e for d,e in zip( data, entr ) )
        window['-SEED-'].update( codecs.encode( seed, 'hex_codec' ).decode( 'ascii' ))

        # A target directory must be selected; use it.  This is where any output will be written.
        # It should usually be a removable volume, but we do not check for this.
        try:
            os.chdir( values['-TARGET-'] )
        except Exception as exc:
            status		= f"Error changing to target directory {values['-TARGET-']!r}: {exc}"
            logging.exception( f"{status}" )
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

        # Confirm the selected Group Threshold requirement
        try:
            g_thr_val		= values['-THRESHOLD-']
            g_thr		= int( g_thr_val )
            assert 0 < g_thr <= len( g_rec ), \
                f"must be an integer between 1 and the number of groups ({len(g_rec)})"
        except Exception as exc:
            status		= f"Error defining group threshold {g_thr_val!r}: {exc}"
            logging.exception( f"{status}" )
            update_seed_recovered( window, values, None )
            continue

        # Produce a summary of the recovered SLIP39 Groups, including any passphrase needed for decryption
        summary			= f"Require {g_thr}/{len(g_rec)} Groups, from: {f', '.join( f'{n}({need}/{size})' for n,(need,size) in g_rec.items())}"
        passphrase		= values['-PASSPHRASE-'].strip()
        if passphrase:
            summary	       += f", decrypted w/ passphrase {passphrase!r}"
        passphrase		= passphrase.encode( 'utf-8' ) if passphrase else b''

        window['-SUMMARY-'].update( summary )

        # Deduce the desired Seed names, defaulting to "SLIP39"
        names			= [
            name.strip()
            for name in ( values['-NAMES-'].strip() or "SLIP39" ).split( ',' )
            if name and name.strip()
        ]

        # Compute the SLIP39 Seed details.  For multiple names, each subsequent slip39.create uses a
        # master_secret produced by hashing the prior master_secret entropy.
        details			= {}
        try:
            master_secret	= codecs.decode( window['-SEED-'].get(), 'hex_codec' )
            for name in names:
                log.info( f"SLIP39 for {name} from master_secret: {codecs.encode( master_secret, 'hex_codec' ).decode( 'ascii' )}" )
                details[name]	= create(
                    name		= name,
                    group_threshold	= group_threshold,
                    master_secret	= master_secret,
                    groups		= g_rec,
                    cryptopaths		= cryptopaths,
                    passphrase		= passphrase,
                )
                master_secret	= hashlib.sha512( master_secret ).digest()[:len(master_secret)]
        except Exception as exc:
            status		= f"Error creating: {exc}"
            logging.exception( f"{status}" )
            update_seed_recovered( window, values, None )
            continue

        if status := update_seed_recovered( window, values, details[names[0]], passphrase=passphrase ):
            continue

        # Finally, if all has gone well -- display the resultant <name>/<filename>, and some derived account details
        name_len		= max( len( name ) for name in details )
        status			= '\n'.join(
            f"{name:>{name_len}} == " + ', '.join( f'{a.crypto} @ {a.path}: {a.address}' for a in details[name].accounts[0] )
            for name in details
        )

        # If we get here, no failure status has been detected, and SLIP39 mnemonic and account
        # details { "name": <details> } have been created; we can now save the PDFs; converted
        # details is now { "<filename>": <details> })
        if event == 'Save':
            try:
                card		= next( c for c in CARD_SIZES if values[f"-CS-{c}"] )
                details		= write_pdfs(
                    names	= details,
                    card	= card,	
                )
            except Exception as exc:
                status		= f"Error saving PDF(s): {exc}"
                logging.exception( f"{status}" )
                continue
            name_len		= max( len( name ) for name in details )
            status		= '\n'.join(
                f"{name:>{name_len}} saved to {values['-TARGET-']}"
                for name in details
            )

    window.close()


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Create and output SLIP39 encoded Ethereum wallet(s) to a PDF file.",
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
                     help="A crypto name and optional derivation path ('../<range>/<range>' allowed); defaults:" \
                     f" {', '.join( f'{c}:{Account.path_default(c)}' for c in Account.CRYPTOCURRENCIES)}" )
    ap.add_argument( '--passphrase',
                     default=None,
                     help="Encrypt the master secret w/ this passphrase, '-' reads it from stdin (default: None/'')" )
    ap.add_argument( 'names', nargs="*",
                     help="Account names to produce")
    args			= ap.parse_args( argv )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    log_cfg['level']		= log_level( args.verbose - args.quiet )
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    try:
        app(
            names		= args.names,
            threshold		= args.threshold,
            group		= args.group,
            cryptocurrency	= args.cryptocurrency,
            passphrase		= args.passphrase,
        )
    except Exception as exc:
        log.exception( f"Failed running App: {exc}" )
        return 1
    return 0
