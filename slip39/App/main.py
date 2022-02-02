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
from ..defaults		import GROUPS, GROUP_THRESHOLD_RATIO, CRYPTO_PATHS

log				= logging.getLogger( __package__ )

font				= ('Courier', 14)

I_kwds				= dict(
    change_submits	= True,
    font		= font,
)
T_kwds				= dict(
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
            ], key='-GROUP-NUMBER-' ) ]]
        ),
        sg.Frame(
            'Group Recovery', [[ sg.Column( [
                [ sg.Input( f'{g_name}', key=f'-G-NAME-{g}', **I_kwds ) ]
                for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
            ], key='-GROUP-NAMES-' ) ]]
        ),
        sg.Frame(
            'Needs at least', [[ sg.Column( [
                [ sg.Input( f'{g_need}', key=f'-G-NEED-{g}', **I_kwds ) ]
                for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
            ], key='-GROUP-NEEDS-' ) ]]
        ),
        sg.Frame(
            'of Cards in Group', [[ sg.Column( [
                [ sg.Input( f'{g_size}', key=f'-G-SIZE-{g}', **I_kwds ) ]
                for g,(g_name,(g_need,g_size)) in enumerate( groups.items() )
            ], key='-GROUP-SIZES-' ) ]]
        ),
    ]
    prefix			= (32, 1)
    inputs			= (32, 1)
    bip39_sample		= "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong"
    layout                      = [
        [
            sg.Frame( 'Seed Data Source', [
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
                    sg.Radio( "BIP-39",         "SD",   key='-SD-BIP-',         default=False,  **B_kwds ),
                    sg.Radio( "SLIP-39",        "SD",   key='-SD-SLIP-',        default=False,  **B_kwds ),
                ],
                [
                    sg.Frame( 'From', [
                        [
                            sg.Text( "Mnemonic(s): ",   key='-SD-DATA-T-',      size=prefix,    **T_kwds ),
                            sg.Multiline( bip39_sample, key='-SD-DATA-',        size=(128,1),   **I_kwds )
                        ],
                    ],                                  key='-SD-DATA-F-',      visible=False ),
                ],
                [
                    sg.Frame( 'Pass', [
                        [
                            sg.Text( "Passphrase (decrypt): ",                  size=prefix,    **T_kwds ),
                            sg.Input( "",               key='-SD-PASS-',                        **I_kwds )
                        ],
                    ],                                  key='-SD-PASS-F-',      visible=False ),
                ],
                [
                    sg.Text( "Seed Data: ", size=prefix, **T_kwds ),
                    sg.Text( f"",                       key='-SD-SEED-',        size=(128,1),   **T_kwds ),
                ],
            ] )
        ],
    ] + [
        [
            sg.Frame( '⊻ Seed Extra Entropy (eg. Die rolls, ...)', [
                [
                    sg.Radio( "Hex",             "SE",  key='-SE-HEX-',         default=True,   **B_kwds ),
                    sg.Radio( "SHA-512 Stretch", "SE",  key='-SE-SHA-',         default=False,  **B_kwds ),
                ],
                [
                    sg.Text( "Entropy: ",               key='-SE-DATA-T-',      size=prefix,    **T_kwds ),
                    sg.Input( "",                       key='-SE-DATA-',        size=(128,1),   **I_kwds ),
                ],
                [
                    sg.Text( "Seed Entropy: ",                                  size=prefix,    **T_kwds ),
                    sg.Text( f"",                       key='-SE-SEED-',        size=(128,1),   **T_kwds ),
                ],
            ] ),
        ]
    ] + [
        [
            sg.Frame( 'Seed Master Secret', [
                [
                    sg.Text( "Seed: ",                                          size=prefix,    **T_kwds ),
                    sg.Text( f"",                       key='-SEED-',           size=(128,1),   **T_kwds ),
                ],
            ] ),
        ],
    ] + [
        [
            sg.Text( "Save PDF to (ie. USB drive): ", size=prefix, **T_kwds ),
            sg.Input( sg.user_settings_get_entry( "-target folder-", ""),  size=inputs, key='-TARGET-', **I_kwds ),
            sg.FolderBrowse( **B_kwds ),
        ],
    ] + [
        [
            sg.Text( "Seed File Name(s): ", size=prefix, **T_kwds ),
            sg.Input( f"{', '.join( names )}",  size=inputs, key='-NAMES-', **I_kwds ),
            sg.Text( "(optional; comma-separated)", **T_kwds ),
        ]
    ] + [
        [
            sg.Text( "Requires recovery of at least: ",        size=prefix, **T_kwds ),
            sg.Input( f"{group_threshold}", key='-THRESHOLD-', size=inputs, **I_kwds ),
            sg.Text( f"(of {len(groups)} SLIP-39 Recovery Groups)", key='-RECOVERY-', **T_kwds ),
        ],
    ] + [
        [
            sg.Text( "Passphrase (encrypt): ",		size=prefix, **T_kwds ),
            sg.Input( f"{passphrase or ''}", key='-PASSPHRASE-', size=inputs, **I_kwds ),
            sg.Text( "(optional; must be remembered separately!!)", **T_kwds ),
        ],
    ] + [
        [
            sg.Frame( 'Groups', [group_body], key='-GROUPS-' ),
        ],
    ] + [
        [
            sg.Button( '+', **B_kwds ), sg.Button( 'Save', **B_kwds ), sg.Exit()
        ],
        [
            sg.Frame(
                'Summary',
                [[ sg.Text( key='-SUMMARY-', **T_kwds ), ]]
            ),
        ],
        [
            sg.Frame(
                'Status',
                [[ sg.Text( key='-STATUS-', **T_kwds ), ]]
            ),
        ],
    ]
    return layout


def app(
    names			= None,
    group			= None,
    threshold			= None,
    cryptocurrency		= None,
    passphrase			= None,
):
    # Convert sequence of group specifications into standard { "<group>": (<needs>, <size>) ... }
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
    seed_data			= None
    seed_entr			= None
    while event not in events_termination:
        # Create window (for initial window.read()), or update status
        if window:
            window['-STATUS-'].update( status or 'OK' )
            window['-RECOVERY-'].update( f"(of {len(groups)} SLIP-39 Recovery Groups)", **T_kwds ),
        else:
            window		= sg.Window( f"{', '.join( names or [ 'SLIP39' ] )} Mnemonic Cards", layout )

        status			= None
        event, values		= window.read()
        logging.info( f"{event}, {values}" )
        if not values or event in events_termination:
            continue

        if event == '+':
            # Add a SLIP39 Groups row
            g			= len(groups)
            name		= f"Group {g+1}"
            needs		= (2,3)
            groups[name] 	= needs
            window.extend_layout( window['-GROUP-NUMBER-'], [[ sg.Text(  f"{g+1}",                          **T_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-NAMES-'],  [[ sg.Input( f"{name}",     key=f"-G-NAME-{g}", **I_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-NEEDS-'],  [[ sg.Input( f"{needs[0]}", key=f"-G-NEED-{g}", **I_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-SIZES-'],  [[ sg.Input( f"{needs[1]}", key=f"-G-SIZE-{g}", **I_kwds ) ]] )  # noqa: 241

        # Respond to changes in the desired Seed Data source, and recover/generate and update the -SD-SEED-
        for seed_data_source in [
                '-SD-128-RND-',
                '-SD-256-RND-',
                '-SD-512-RND-',
                '-SD-128-FIX-',
                '-SD-256-FIX-',
                '-SD-512-FIX-',
                '-SD-BIP-',
                '-SD-SLIP-',
        ]:
            if values.get( seed_data_source ) and seed_data != seed_data_source:
                seed_data	= seed_data_source
                # Changed Seed Data source!
                if 'FIX' in seed_data:
                    window['-SD-DATA-T-'].update( f"Hex data: " )
                    window['-SD-DATA-F-'].update( visible=True  )
                    window['-SD-PASS-F-'].update( visible=False )
                elif 'RND' in seed_data:
                    window['-SD-DATA-F-'].update( visible=False )
                    window['-SD-PASS-F-'].update( visible=False )
                elif 'BIP' in seed_data:
                    window['-SD-DATA-T-'].update( f"BIP-39 Mnemonic: " )
                    window['-SD-DATA-F-'].update( visible=True )
                    window['-SD-PASS-F-'].update( visible=True )
                elif 'SLIP' in seed_data:
                    window['-SD-DATA-T-'].update( f"SLIP-39 Mnemonics: " )
                    window['-SD-DATA-F-'].update( visible=True )
                    window['-SD-PASS-F-'].update( visible=True )
        if 'FIX' in seed_data:
            bits		= int( seed_data.split( '-' )[2] )
            try:
                # 0-fill and truncate any supplied hex data to the desired bit length
                data		= f"{values['-SD-DATA-']:<0{bits//4}.{bits//4}}"
                master_secret = codecs.decode( data, 'hex_codec' )
            except Exception as exc:
                status		= f"Invalid Hex for {bits}-bit fixed seed: {exc}"
                continue
        elif 'BIP' in seed_data:
            try:
                master_secret	= recover_bip39(
                    mnemonic	= values['-SD-DATA-'].strip(),
                    passphrase	= values['-SD-PASS-'].strip().encode( 'UTF-8' )
                )
            except Exception as exc:
                status	= f"Invalid BIP-39 recovery mnemonic: {exc}"
                continue
        elif 'SLIP' in seed_data:
            try:
                master_secret	= recover(
                    mnemonics	= values['-SD-DATA-'].strip().split( '\n' ),
                    passphrase	= values['-SD-PASS-'].strip().encode( 'UTF-8' )
                )
            except Exception as exc:
                status	= f"Invalid SLIP-39 recovery mnemonics: {exc}"
                continue
        else: # Random.  Regenerated each time through.
            bits		= int( seed_data.split( '-' )[2] )
            master_secret	= random_secret( bits // 8 )

        # Compute the Seed Data as hex.  Will be 128-, 256- or 512-bit hex data.
        window['-SD-SEED-'].update( codecs.encode( master_secret, 'hex_codec' ).decode( 'ascii' ))

        # Respond to changes in the Seed Entropy, and recover/generate the -SE-SEED-.  It is
        # expected to be exactly the same size as the -SD-SEED- data.
        for seed_entr_source in [
            '-SE-HEX-',
            '-SE-SHA-',
        ]:
            if values.get( seed_entr_source ) and seed_entr != seed_entr_source:
                seed_entr	= seed_entr_source
                # Changed Seed Entropy source!
                if 'HEX' in seed_entr:
                    window['-SE-DATA-T-'].update( f"Entropy (hex): " )
                else:
                    window['-SE-DATA-T-'].update( f"Entropy (die rolls, etc.): " )

        bits			= len( window['-SD-SEED-'].get() ) * 4
        if 'HEX' in seed_entr:
            try:
                # 0-fill and truncate any supplied hex data to the desired bit length
                data		= f"{values['-SE-DATA-']:<0{bits//4}.{bits//4}}"
                master_entropy	= codecs.decode( data, 'hex_codec' )
            except Exception as exc:
                status		= f"Invalid Hex for {bits}-bit extra seed entropy: {exc}"
                continue
        else:
            try:
                # SHA-512 stretch and possibly truncate
                stretch		= hashlib.sha512()
                stretch.update( values['-SE-DATA-'].encode( 'UTF-8' ))
                master_entropy	= stretch.digest()[:bits//8]
            except Exception as exc:
                status		= f"Invalid data for {bits}-bit extra seed entropy: {exc}"
                continue

        # Compute the Seed Entropy as hex.  Will be 128-, 256- or 512-bit hex data.
        window['-SE-SEED-'].update( codecs.encode( master_entropy, 'hex_codec' ).decode( 'ascii' ))

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
                g_rec[grp] 	= int( values[f"-G-NEED-{g}"] or 0 ), int( values[f"-G-SIZE-{g}"] or 0 )
            except Exception as exc:
                status		= f"Error defining group {g+1} {grp!r}: {exc}"
                logging.exception( f"{status}" )
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
            continue

        summary			= f"Require {g_thr}/{len(g_rec)} Groups, from: {f', '.join( f'{n}({need}/{size})' for n,(need,size) in g_rec.items())}"
        passphrase		= values['-PASSPHRASE-'].strip()
        if passphrase:
            summary	       += f", decrypted w/ passphrase {passphrase!r}"
        window['-SUMMARY-'].update( summary )

        # Deduce the desired Seed names, defaulting to "SLIP39"
        names			= [
            name.strip()
            for name in ( values['-NAMES-'].strip() or "SLIP39" ).split( ',' )
            if name and name.strip()
        ]

        # Compute the SLIP39 Seed details
        details			= {}
        try:
            for name in names:
                details[name]	= create(
                    name		= name,
                    group_threshold	= group_threshold,
                    groups		= g_rec,
                    cryptopaths		= cryptopaths,
                    passphrase		= passphrase.encode( 'utf-8' ) if passphrase else b'',
                )
        except Exception as exc:
            status		= f"Error creating: {exc}"
            logging.exception( f"{status}" )
            continue

        # If we get here, no failure status has been detected, and SLIP39 mnemonic and account
        # details { "name": <details> } have been created; we can now save the PDFs; converted
        # details is now { "<filename>": <details> })
        if event == 'Save':
            try:
                details		= write_pdfs(
                    names	= details,
                )
            except Exception as exc:
                status		= f"Error saving PDF(s): {exc}"
                logging.exception( f"{status}" )
                continue

        # Finally, if all has gone well -- display the resultant <name>/<filename>, and some derived account details
        name_len		= max( len( name ) for name in details )
        status			= '\n'.join(
            f"{name:>{name_len}} == " + ', '.join( f'{a.crypto} @ {a.path}: {a.address}' for a in details[name].accounts[0] )
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
                     help=f"A crypto name and optional derivation path ('../<range>/<range>' allowed); defaults: {', '.join( f'{c}:{Account.path_default(c)}' for c in Account.CRYPTOCURRENCIES)}" )
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
