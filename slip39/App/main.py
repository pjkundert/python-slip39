import argparse
import logging
import math
import os

import PySimpleGUI as sg

from ..types		import Account
from ..api		import create, group_parser
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
    prefix			= (30,1)
    layout			= [
        [
            sg.Text( "Save PDF to (ie. USB drive): ", size=prefix, **T_kwds ),
            sg.Input( sg.user_settings_get_entry( "-target folder-", ""), k='-TARGET-', **I_kwds ),
            sg.FolderBrowse( **B_kwds )
        ],
    ] + [
        [
            sg.Text( "Seed File Name(s): ", size=prefix, **T_kwds ),
            sg.Input( f"{', '.join( names )}", key='-NAMES-', **I_kwds ),
            sg.Text( "(comma-separted)", **T_kwds ),
        ]
    ] + [
        [
            sg.Text( "Requires recovery of at least: ", size=prefix, **T_kwds ),
            sg.Input( f"{group_threshold}", key='-THRESHOLD-', **I_kwds ),
            sg.Text( f"of {len(groups)} SLIP-39 Recovery Groups", key='-RECOVERY-', **T_kwds ),
        ],
    ] + [
        [
            sg.Text( "Passphrase to encrypt Seed: ", size=prefix, **T_kwds ),
            sg.Input( f"{passphrase or ''}", key='-PASSPHRASE-', **I_kwds ),
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
    while event not in (sg.WIN_CLOSED, 'Exit',):
        # Create window (for initial window.read()), or update status
        if window:
            window['-STATUS-'].update( status or 'OK' )
            window['-RECOVERY-'].update( f"of {len(groups)} SLIP-39 Recovery Groups", **T_kwds ),
        else:
            window		= sg.Window( f"{', '.join( names )} Mnemonic Cards", layout )

        status			= None
        event, values		= window.read()
        logging.info( f"{event}, {values}" )
        if not values:
            continue

        if '-TARGET-' in values:
            # A target directory has been selected;
            try:
                os.chdir( values['-TARGET-'] )
            except Exception as exc:
                status		= f"Error changing to target directory {values['-TARGET-']}: {exc}"
                logging.exception( f"{status}" )
                continue

        if event == '+':
            g			= len(groups)
            name		= f"Group {g+1}"
            needs		= (2,3)
            groups[name] 	= needs
            window.extend_layout( window['-GROUP-NUMBER-'], [[ sg.Text(  f"{g+1}",                          **T_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-NAMES-'],  [[ sg.Input( f"{name}",     key=f"-G-NAME-{g}", **I_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-NEEDS-'],  [[ sg.Input( f"{needs[0]}", key=f"-G-NEED-{g}", **I_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-SIZES-'],  [[ sg.Input( f"{needs[1]}", key=f"-G-SIZE-{g}", **I_kwds ) ]] )  # noqa: 241

        try:
            g_thr_val		= values['-THRESHOLD-']
            g_thr		= int( g_thr_val )
        except Exception as exc:
            status		= f"Error defining group threshold {g_thr_val}: {exc}"
            logging.exception( f"{status}" )
            continue

        # Collect up the specified Group names; ignores groups with an empty name
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

        summary			= f"Require {g_thr}/{len(g_rec)} Groups, from: {f', '.join( f'{n}({need}/{size})' for n,(need,size) in g_rec.items())}"
        passphrase		= values['-PASSPHRASE-'].strip()
        if passphrase:
            summary	       += f", decrypted w/ passphrase {passphrase!r}"
        window['-SUMMARY-'].update( summary )

        names			= [
            name.strip()
            for name in values['-NAMES-'].split( ',' )
            if name and name.strip()
        ]
        details			= {}
        try:
            for name in names or [ "SLIP39" ]:
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

        # If we get here, no failure status has been detected; we could save (details is now { "<filename>": <details> })
        if event == 'Save':
            details		= write_pdfs(
                names	= details,
            )

        name_len		= max( len( name ) for name in details )
        status			= '\n'.join(
            f"{name:>{name_len}} == " + ', '.join( f'{a.crypto} @ {a.path}: {a.address}' for a in details[name].accounts[0] )
            for name in details
        )

    window.close()


def main( argv=None ):
    ap				= argparse.ArgumentParser(
        description = "Create and output SLIP39 encoded Ethereum wallet(s) to a PDF file.",
        epilog = "" )
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
