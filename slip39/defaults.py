
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

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

#
# HD Wallet Derivation Paths (Standard BIP-44 / Trezor)
#
#     https://wolovim.medium.com/ethereum-201-hd-wallets-11d0c93c87f7
#
# BIP-44 defines the purpose of each depth level:
#    m / purpose’ / coin_type’ / account’ / change / address_index
#
# Use https://iancoleman.io/bip39/ to confirm the derivations
#

# Default group_threshold / required ratios and groups (with varying styles of definition)
GROUP_REQUIRED_RATIO		= 1/2   # default to 1/2 of group members, rounded up
GROUP_THRESHOLD_RATIO		= 1/2   # default to 1/2 of groups, rounded up
GROUPS				= [
    "First1",
    "Second(1/1)",
    "Fam(4)",
    "Frens3/6"
]

THEME				= 'DarkAmber'   # PySimpleGUI Theme
FONTS				= dict(
    sans	= 'helvetica',
    mono	= 'sourcecode',  # UTF-8 monospaced w/ "━": dejavu, inconsolata, noto, overpass, sourcecode
)

#                                  Y      X       Margin
BUSINESS_CARD			= (2,     3+1/2), 1/32  # noqa: E241
CREDIT_CARD			= (2+1/4, 3+3/8), 1/32
INDEX_CARD			= (3,     5),     1/16  # noqa: E241
HALF_LETTER			= (13.5/3,7+3/4), 1/8   # noqa: E241 (actually 2/letter, 3/legal)
THIRD_LETTER			= (13.5/4,7+3/4), 1/8   # noqa: E241 (actually 3/letter, 4/legal)
QUARTER_LETTER			= (10.5/4,7+3/4), 1/8   # noqa: E241 (actually 4/letter, 5/legal)
PHOTO_CARD			= (3+1/2, 5+1/2), 1/16  # prints on 4x6 photo paper w/ 1/4" default outer border

# SLIP-39 Mnemonic Card Sizes
CARD				= 'business'
CARD_SIZES			= dict(
    business	= BUSINESS_CARD,
    credit	= CREDIT_CARD,
    index	= INDEX_CARD,
    half	= HALF_LETTER,
    third	= THIRD_LETTER,
    quarter	= QUARTER_LETTER,
    photo	= PHOTO_CARD,
)

# Paper Wallet Bill Sizes, by default on PAPER format paper
WALLET				= 'quarter'
WALLET_SIZES			= dict(
    half	= HALF_LETTER,
    third	= THIRD_LETTER,
    quarter	= QUARTER_LETTER,
)

PAGE_MARGIN			= 1/4  # Typical printers cannot print within 1/4" of edge

MM_IN				= 25.4
PT_IN				= 72

PAPER				= 'Letter'
PAPER_FORMATS			= dict(
    Letter	= 'Letter',
    Legal	= 'Legal',
    A4		= 'A4',
    Photo	= (int( 4 * MM_IN ), int( 6 * MM_IN )),
)

ORIENTATION			= 'portrait'

# The available GUI controls Layout Options
LAYOUT				= 'Backup'
LAYOUT_OPTIONS			= [
    'Backup',
    'Create',
    'Recover',
    'Pro',
]
LAYOUT_BAK			= 0
LAYOUT_CRE			= 1
LAYOUT_REC			= 2
LAYOUT_PRO			= 3

BITS_DEFAULT			= 128
BITS				= (128, 256, 512)
BITS_BIP39			= BITS + (160, 192, 224)

MNEM_ROWS_COLS			= {
    20:	( 7, 3),		# 128-bit seed
    33:	(11, 3),		# 256-bit seed
    59:	(12, 5),		# 512-bit seed, eg. from BIP-39 (Unsupported on Trezor)
}

# Separators for groups of Mnemonics, and those that indicate the continuation/last line of a
# Mnemonic phrase
MNEM_PREFIX			= {
    20: '{',
    33: '╭╰',
    59: '┌├└',
}
MNEM_LAST			= '╰└{'
MNEM_CONT			= '╭┌├'

BAUDRATE			= 115200

FILENAME_KEYWORDS		= ['name', 'date', 'time', 'crypto', 'path', 'address']
FILENAME_FORMAT			= "{name}-{date}+{time}-{crypto}-{address}.pdf"

# Default Crypto accounts (and optional paths) to generate
CRYPTO_PATHS			= ('ETH', 'BTC')

__d				= "55"
__m				= "88"
__o				= "BB"
__h				= "DD"
__f				= "FF"
COLOR				= [
    # Primary
    f"0x{__o}{__o}{__f}",  # Blue
    f"0x{__o}{__f}{__o}",  # Green
    f"0x{__f}{__o}{__o}",  # Red
    # Secondary
    f"0x{__o}{__f}{__f}",  # Cyan,
    f"0x{__f}{__o}{__f}",  # Magenta
    f"0x{__f}{__f}{__o}",  # Yellow
    # Tertiary
    f"0x{__o}{__h}{__f}",  # Ocean
    f"0x{__o}{__f}{__h}",  # Turquoise
    f"0x{__f}{__o}{__h}",  # Red-Magenta
    f"0x{__h}{__o}{__f}",  # Violet
    f"0x{__h}{__f}{__o}",  # Lime
    f"0x{__f}{__h}{__o}",  # Orange
    # Other
    f"0x{__o}{__h}{__h}",  # Light Cyan
    f"0x{__h}{__o}{__h}",  # Light Magenta
    f"0x{__h}{__h}{__o}",  # Light Yellow
    # Greys
    f"0x{__h}{__h}{__h}",  # Light grey,
    f"0x{__m}{__m}{__m}",  # Medium grey,
    f"0x{__d}{__d}{__d}",  # Dark grey,
]

# We'll default to 30-second intervals for querying Etherscan for Gas, ETH, ERC-20 Pricing info
ETHERSCAN_MEMO_MAXAGE		= 30
ETHERSCAN_MEMO_MAXSIZE		= None
# For token prices, default to 5 minute refreshes
TOKPRICES_MEMO_MAXAGE		= 5*60
TOKPRICES_MEMO_MAXSIZE		= None

SMTP_TO				= "licensing@dominionrnd.com"
SMTP_FROM			= "no-reply@licensing.dominionrnd.com"

# Invoice options.  Presently, only highly-liquid ERC-20 tokens present in Ethereum AMM
# (Automatic Market Maker) systems should be used in invoices, since we use 1Inch's "Off-Chain
# Oracle" smart contract to get current market values.  This prevents us from needing to "trust"
# anyone to obtain current prices for cryptocurrencies -- if you have access to an Ethereum
# blockchain (either locally or via an HTTPS API like Alchemy), then we can securely and reliably
# get current prices.  To avoid conflicts, by convention we upper-case symbols, lower-case full
# names.
INVOICE_FORMAT			= 'totalize'  # 'presto'  # 'orgtbl'
INVOICE_ROWS			= 60  # rows on invoice; each page, about 1/2 that number of line-items
INVOICE_DESCRIPTION_MAX		= 48  # This may seem low; full-precision Prices, 8-dec. Cryptos need room
INVOICE_CURRENCY		= "USD"
INVOICE_PROXIES			= {
    "USD":		"USDC",
    "us dollar":	"USDC",
    "ETH":		"WETH",
    "ethereum":		"WETH",
    "BTC":		"WBTC",
    "bitcoin":		"WBTC",
}

# Invoice times; very explicit about timezones, b/c short zone names are non-deterministic
INVOICE_DUE			= dict( months=1 )      # Default terms: Net 1 month (~30 days)
INVOICE_STRFTIME		= "%c %z %Z"            # "Wed Aug 16 21:30:00 1988 +0000 UTC"
