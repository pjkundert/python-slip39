
#
# Python-slip39 -- Ethereum SLIP-39 Account Generation and Recovery
#
# Copyright (c) 2021, Dominion Research & Development Corp.
#
# Python-slip39 is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. See the LICENSE file at the top of the source tree.
#
# Python-slip39 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#

PATH_ETH_DEFAULT		= "m/44'/60'/0'/0/0"

# Default group_threshold / required ratios and groups (with varying styles of definition)
GROUP_REQUIRED_RATIO		= 1/2   # default to 1/2 of group members, rounded up
GROUP_THRESHOLD_RATIO		= 1/2   # default to 1/2 of groups, rounded up
GROUPS				= [
    "First1",
    "Second(1/1)",
    "Fam(4)",
    "Fren2/6"
]

FONTS				= dict(
    sans	= 'helvetica',
    mono	= 'courier',
)

#                                  Y      X       Margin
CREDIT_CARD			= (2+1/4, 3+3/8), 1/16
INDEX_CARD			= (3,     5),     1/8   # noqa: E241
BUSINESS_CARD			= (2,     3+1/2), 1/32  # noqa: E241
HALF_LETTER			= (4+1/2, 8),     1/4   # noqa: E241 (actually, 2/letter, 3/legal)
FULL_LETTER			= (8,    10),     1/4   # noqa: E241

CARD				= 'index'
CARD_SIZES			= dict(
    credit	= CREDIT_CARD,
    index	= INDEX_CARD,
    business	= BUSINESS_CARD,
    half	= HALF_LETTER,
    full	= FULL_LETTER
)

PAGE_MARGIN			= 1/4  # Typical printers cannot print within 1/4" of edge

PAPER				= 'Letter'

BITS				= (128, 256, 512)
BITS_DEFAULT			= 128

MNEM_ROWS_COLS			= {
    20:	( 7, 3),		# 128-bit seed
    33:	(11, 3),		# 256-bit seed
    59:	(12, 5),		# 512-bit seed, eg. from BIP-39 (Unsupported on Trezor hardware wallet)
}
