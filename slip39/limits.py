
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

import logging

from .util		import user_name_full

from crypto_licensing	import authorized, Agent, LicenseIncompatibility, domainkey_service

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2025 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

#
# Limits, Prices, Fees and Payment details deduced from License(s)
#
#     Load/Create the SLIP-39 App owner's keypair.  The User's email address and Full Name is
# required, and must be saved.  We will create the Owner's Keypair, and request a License specific to
# this client, containing eg.
#
#     "client":{
#         "name":"Perry Kundert <perry@kundert.ca>",
#         "pubkey":"xyZHsgdsrtA83kM/C/LUN8Y2If+BIvcs1X4nYw0maBc="
#     },
#
# When ready (or a generic License is already) available, we can issue it with this agent as author:
#
#    "license":{
#        "author":{
#            "name":"Perry Kundert <perry@kundert.ca>",
#            "product":"SLIP-39 App Owner",
#            "pubkey":"xyZHsgdsrtA83kM/C/LUN8Y2If+BIvcs1X4nYw0maBc="
#            "service":"slip-39-app-owner"
#        },
#
#     It is assumed that the Owner's email address + Full Name is sufficiently unique, and forms the
# basis for issuing Licenses that can be migrated across the owner's machine(s).  It is also used
# for creating + encrypting and subsequently re-loading the Owner's Public Key, to which Licenses
# are issued.
#
#     We use licensing.authorized to navigate the Keypair load/create and license load/issue
# process.
#
# slip39.gui
# ----------
#
#     If in the slip39.gui, several panes are presented guiding the user through the process, which
# can be undertaken manually if the user prefers to remain offline.  A QR code presents the required
# URL to issue the license.
#

log				= logging.getLogger( "limits" )


def authorize( email, full_name=None, **kwds ):

    if not full_name:
        full_name		= user_name_full()
    if not full_name or not email:
        raise LicenseIncompatibility( f"Owner name {full_name!r} and email {email!r} required for licensing" )
    password			= f"{full_name} <{email}>"
    product			= "SLIP-39 App Owner"
    service			= domainkey_service( product )
    author			= Agent(
        domain		= "slip39.com",
        name		= "Perry Kundert (SLIP-39)",
        product		= "SLIP-39 App",
        pubkey		= "qtHHsgdsrtA83kM/C/LUN8Y2If+BIvcs1X4nYw0m0w4=",
        service		= "slip-39-app",
    )
    client			= Agent(
        name		= full_name,
        product		= product,
        service		= service,
    )
    auth_flow			= authorized(
        author		= author,
        client		= client,
        username	= email,
        password	= password,
        **kwds
    )
    for key,lic in auth_flow:
        log.normal( f"SLIP-39 Owner key: {key}: {lic}" )
        credentials	= ( yield key,lic )
        auth_flow.send( credentials )


'''
def owner_keypair( email, full_name=None ):

    passwordf			= f"{full_name} <{email}>"
    keypair			= licensing.registered(
        why		= "SLIP-39 Owner Keypair"
        basename	= "slip-39-owner",
        username	= email,
        password	= password,
        registering	= True,
    )
    return email,full_name,keypair,keypair.into_keypair(
        username,	= username,
        password	= password,
    )


def owner_license( email, full_name=None, confirm=None ):

    email,full_name,keypair,keypair_raw = owner_keypair( email, full_name )

    dependencies	= []
    for _from,prov in licensing.load(
            basename 	= "slip-39-app",
    )

    lic				= licensing.license(
        author		= licensing.Agent(
            name	= f"{full_name} <{email>}",
            product	= "SLIP-39 Owner",
            service	= "slip-39-owner",
            keypair	= keypair_raw,
        ),

        why		= "SLIP-39 Owner License",
        basename	= "slip-39-owner",
    )
'''
