import argparse
import logging
import math
import sys

import PySimpleGUI as sg

from ..types		import Account
from ..api		import create, group_parser
from ..util		import log_level, log_cfg
from ..defaults		import GROUPS, GROUP_THRESHOLD_RATIO

font				= ('Sans', 12)

I_kwds				= dict(
    change_submits	= True,
    font		= font,
)

T_kwds				= dict(
    font		= font,
)


def groups_layout( names, group_threshold, groups ):
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

    layout			= [
        [
            sg.Input( f"{', '.join( names )}", key='-NAMES-', **I_kwds ),
            sg.Text( "Requires collection of at least", **T_kwds ),
            sg.Input( f"{group_threshold}", key='-THRESHOLD-', **I_kwds ),
            sg.Text( f" of {len(groups)} SLIP-39 Recovery Groups", **T_kwds ),
        ],
    ] + [
        [
            sg.Frame( 'Groups', [group_body], key='-GROUPS-' ),
        ],
    ] + [
        [
            sg.Button( '+' ), sg.Button( 'Generate' ), sg.Exit()
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


def app( names, group_threshold, groups, cryptopaths ):
    sg.theme( 'DarkAmber' )

    layout			= groups_layout( names, group_threshold, groups )
    window			= None
    status			= None
    event			= False
    while event not in (sg.WIN_CLOSED, 'Exit',):
        if window:
            window['-STATUS-'].update( status or 'OK' )
        else:
            window		= sg.Window( f"{', '.join( names )} Mnemonic Cards", layout )

        status			= None
        event, values		= window.read()
        logging.info( f"{event}, {values}" )

        if event == '+':
            g			= len(groups)
            name		= f"Group {g+1}"
            needs		= (1,2)
            groups[name] 	= needs
            window.extend_layout( window['-GROUP-NUMBER-'], [[ sg.Text(  f"{g+1}",                          **T_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-NAMES-'],  [[ sg.Input( f"{name}",     key=f"-G-NAME-{g}", **I_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-NEEDS-'],  [[ sg.Input( f"{needs[0]}", key=f"-G-NEED-{g}", **I_kwds ) ]] )  # noqa: 241
            window.extend_layout( window['-GROUP-SIZES-'],  [[ sg.Input( f"{needs[1]}", key=f"-G-SIZE-{g}", **I_kwds ) ]] )  # noqa: 241

        if event == 'Generate':
            try:
                g_thr_val	= values['-THRESHOLD-']
                g_thr		= int( g_thr_val )
            except Exception as exc:
                status		= f"Error defining group threshold {g_thr_val}: {exc}"
                logging.exception( f"{status}" )
                continue

            g_rec		= {}
            status		= None
            for g in range( 16 ):
                nam_idx		= f"-G-NAME-{g}"
                if nam_idx not in values:
                    break
                try:
                    nam		= values[nam_idx]
                    req,siz	= int( values[f"-G-NEED-{g}"] ), int( values[f"-G-SIZE-{g}"] )
                    g_rec[nam] 	= (req, siz)
                except Exception as exc:
                    status	= f"Error defining group {g+1}: {exc}"
                    logging.exception( f"{status}" )
                    continue

            summary		= f"Require {g_thr}/{len(g_rec)} Groups, from: {f', '.join( f'{n}({need}/{size})' for n,(need,size) in g_rec.items())}" 
            window['-SUMMARY-'].update( summary )
            if status is None:
                details		= {}
                try:
                    for name in names:
                        details[name]	= create(
                            name		= name,
                            group_threshold	= group_threshold,
                            groups		= g_rec,
                            cryptopaths		= cryptopaths,
                    )
                except Exception as exc:
                    status	= f"Error creating: {exc}"
                    logging.exception( f"{status}" )
                    continue

                status		= 'OK'
                for n in names:
                    accts	= ', '.join( f'{a.crypto} @ {a.path}: {a.address}' for a in details[n].accounts[0] )
                    status     += f"; {accts}"

    window.close()

    return 0


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
    ap.add_argument( 'names', nargs="*",
                     help="Account names to produce")
    args			= ap.parse_args( argv )

    # Set up logging; also, handle the degenerate case where logging has *already* been set up (and
    # basicConfig is a NO-OP), by (also) setting the logging level
    log_cfg['level']		= log_level( args.verbose - args.quiet )
    logging.basicConfig( **log_cfg )
    if args.verbose:
        logging.getLogger().setLevel( log_cfg['level'] )

    names			= args.names or [ 'SLIP-39' ]
    groups			= dict(
        group_parser( g )
        for g in args.group or GROUPS
    )
    group_threshold		= args.threshold or math.ceil( len( groups ) * GROUP_THRESHOLD_RATIO )

    cryptopaths			= []
    for crypto in args.cryptocurrency or ['ETH', 'BTC']:
        try:
            crypto,paths	= crypto.split( ':' )
        except ValueError:
            crypto,paths	= crypto,None
        cryptopaths.append( (crypto,paths) )

    sys.exit(
        app(
            names		= names,
            group_threshold	= group_threshold,
            groups		= groups,
            cryptopaths		= cryptopaths,
        )
    )
