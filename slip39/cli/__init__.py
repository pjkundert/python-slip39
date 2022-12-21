
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

from __future__          import annotations

import click
import json
import logging
import string

from ..			import addresses as slip39_addresses
from ..util		import commas, log_cfg, log_level, input_secure
from ..defaults		import BITS

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

"""
Provide basic CLI access to the slip39 API.

Output generally defaults to JSON.  Use -v for more details, and --no-json to emit standard text output instead.
"""

log				= logging.getLogger( __package__ )


@click.group()
@click.option('-v', '--verbose', count=True)
@click.option('-q', '--quiet', count=True)
@click.option( '--json/--no-json', default=True, help="Output JSON (the default)")
def cli( verbose, quiet, json ):
    cli.verbosity		= verbose - quiet
    log_cfg['level']		= log_level( cli.verbosity )
    logging.basicConfig( **log_cfg )
    if verbose or quiet:
        logging.getLogger().setLevel( log_cfg['level'] )
    cli.json			= json
cli.verbosity			= 0  # noqa: E305
cli.json			= False


@click.command()
@click.option( "--crypto", help="The cryptocurrency address to generate (default: BTC)" )
@click.option( "--paths", help="The HD wallet derivation path (default: the standard path for the cryptocurrency; if xpub, omits leading hardened segments by default)" )
@click.option( "--secret", required=True, help="A hex seed or '{x,y,z}{pub,prv}...' x-public/private key to derive HD wallet addresses from; '-' reads it from stdin" )
@click.option( "--format", help="legacy, segwit, bech32 (default: standard for cryptocurrency or '{x,y,z}{pub/prv}...' key)" )
@click.option( '--unbounded/--no-unbounded', default=False, help="Allow unbounded sequences of addresses")
def addresses( crypto, paths, secret, format, unbounded ):
    if secret == '-':
        secret			= input_secure( 'Master secret hex: ', secret=True )
    elif secret and ( secret.lower().startswith( '0x' )
                      or all( c in string.hexdigits for c in secret )):
        log.warning( "It is recommended to not use '-s|--secret <hex>'; specify '-' to read from input" )
    if secret and secret.lower().startswith('0x'):
        secret			= secret[2:]
    if not secret:
        log.error( f"Provide a random {commas( BITS, final='or' )}-bit Seed via --secret" )
    if cli.json:
        click.echo( "[" )
    for i,(cry,pth,adr) in enumerate( slip39_addresses(
            master_secret	= secret,
            crypto		= crypto,
            paths		= paths,
            format		= format,
            allow_unbounded	= unbounded
    )):
        if cli.json:
            if i:
                click.echo( "," )
            if cli.verbosity > 0:
                click.echo( f"    [{json.dumps( cry )+',':6} {json.dumps( pth )+',':21} {json.dumps( adr )}]", nl=False )
            else:
                click.echo( f"    {json.dumps( adr )}", nl=False )
        else:
            if cli.verbosity > 0:
                click.echo( f"{cry:5} {pth:20} {adr}" )
            else:
                click.echo( f"{adr}" )
    if cli.json:
        click.echo( "\n]" )


cli.add_command( addresses )
