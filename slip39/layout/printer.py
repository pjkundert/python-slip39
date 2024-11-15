
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

import logging
import re
import subprocess
import sys

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( __package__ )


def printers_available():
    """
    On macOS, find any available printers that appear to be available:

        printer Canon_G6000_series is idle.  enabled since Thu  3 Mar 09:24:56 2022
                ...
                Description: Canon G6000
                Alerts: none
                ...
        printer Marg_s_Brother_HL_L2360D is idle.  enabled since Wed 15 Sep 12:19:48 2021
                ...
                Description: Marg's Brother HL-L2360D
                Alerts: offline-report
                ...

    Yields a sequence of their names: (<system>,<long>), ...
    """
    if sys.platform == 'darwin':
        command		= [ '/usr/bin/lpstat', '-lt' ]
        command_input	= None
    else:
        raise NotImplementedError( f"Printing not supported on platform {sys.platform}" )

    subproc			= subprocess.run(
        command,
        input		= command_input,
        capture_output	= True,
        encoding	= 'UTF-8'
    )
    assert subproc.returncode == 0 and subproc.stdout, \
        f"{' '.join( command )!r} command failed, or no output returned"

    if sys.platform == 'darwin':
        system,human,ok		= None,None,None
        for li in subproc.stdout.split( '\n' ):
            printer		= re.match( r"^printer\s+([^\s]+)", li )
            if printer:
                system,human,ok	= printer.group(1).strip(),None,None
                continue
            descr		= re.match( r"^\s+Description:(.*)", li )
            if descr:
                human		= descr.group(1).strip()
                continue
            alerts		= re.match( r"^\s+Alerts:(.*)", li )
            if alerts:
                ok		= 'offline' not in alerts.group(1)
                log.info( f"Printer: {human}: {alerts.group(1)}" )
            if ok:
                yield system,human
                system,human,ok	= None,None,None


def printer_output(
    binary,			# Raw data for printer
    printer		= None,
    orientation		= None,
    paper_format	= None,
    double_sided	= None,
):
    """Output raw binary data directly to the printer, eg.

        ... | lpr -P "Canon_G6000_series" -o media=Letter -o sides=one-sided -o job-sheets=secret

    """
    double_sided		= True if double_sided is None else bool( double_sided )
    if sys.platform == 'darwin':
        command			= [ '/usr/bin/lpr', '-o', 'sides=one-sided' ]
        command_input		= binary

        # Find the desired printer's system name; otherwise use default printer
        printer_system		= None
        if printer:
            printer_list	= list( printers_available() )
            for system,human in printer_list:
                if human.lower() == printer.lower() or system.lower() == printer.lower():
                    printer_system = system
            assert printer_system, \
                f"Couldn't locate printer matching {printer!r}, in {', '.join( h for s,h in printer_list )}"
        if printer_system:
            command	       += [ '-P', printer_system ]
        if paper_format:
            command    	       += [ '-o', f"media={paper_format.capitalize()}" ]
        if orientation:
            # -o orientation-requested=N   Specify portrait (3) or landscape (4) orientation
            N		= { 'p': 3, 'l': 4 }[orientation.lower()[0]]
            command	       += [ '-o', f"orientation-requested={N}" ]
        if double_sided:
            # Regardless of desired orientation, layout assumes long-edge double-sided
            command	       += [ '-o', "sides=two-sided-long-edge" ]

    log.info( f"Printing via: {' '.join( command )}" )
    subproc			= subprocess.run(
        command,
        input		= command_input,
        capture_output	= True,
    )
    assert subproc.returncode == 0, \
        f"{' '.join( command )!r} command failed"
