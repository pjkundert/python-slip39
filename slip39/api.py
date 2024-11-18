
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

import base58
import codecs
import hashlib
import itertools
import json
import logging
import math
import re
import string
import warnings

from functools		import wraps
from collections	import namedtuple
from typing		import Dict, List, Sequence, Tuple, Optional, Union, Callable

from shamir_mnemonic	import EncryptedMasterSecret, split_ems
from shamir_mnemonic.shamir import _random_identifier, RANDOM_BYTES

import hdwallet
from hdwallet		import cryptocurrencies

from .defaults		import (
    BITS_DEFAULT, BITS, MNEM_ROWS_COLS, GROUPS, GROUP_REQUIRED_RATIO, GROUP_THRESHOLD_RATIO, CRYPTO_PATHS
)
from .util		import ordinal, commas, is_mapping
from .recovery		import produce_bip39, recover_bip39, recover as recover_slip39

__author__                      = "Perry Kundert"
__email__                       = "perry@dominionrnd.com"
__copyright__                   = "Copyright (c) 2022 Dominion Research & Development Corp."
__license__                     = "Dual License: GPLv3 (or later) and Commercial (see LICENSE)"

log				= logging.getLogger( __package__ )


# Support for private key encryption via BIP-38 and Ethereum JSON wallet is optional; pip install slip39[wallet]
paper_wallet_issues		= []
try:
    from Crypto.Cipher	import AES
    from Crypto.Protocol.KDF import scrypt
except ImportError as exc:
    AES				= None
    scrypt			= None
    message			= f"Unable to support Paper Wallet output: {exc}"
    warnings.warning( message, ImportWarning )
    if log.isEnabledFor( logging.DEBUG ):
        log.exception( message )
    paper_wallet_issues.append( message )

try:
    import eth_account
except ImportError as exc:
    eth_account			= None
    message			= f"Unable to support Paper Wallet output: {exc}"
    warnings.warning( message, ImportWarning )
    if log.isEnabledFor( logging.DEBUG ):
        log.exception( message )
    paper_wallet_issues.append( message )


def paper_wallet_available():
    """Determine if encrypted BIP-38 and Ethereum JSON Paper Wallets are available."""
    available			= AES and scrypt and eth_account
    if not available:
        log.warning( f"Paper Wallets unavailable; perhaps run: 'python3 -m pip install slip39[gui,wallet]': {', '.join( paper_wallet_issues )}" )
    return available


def path_edit(
    path: str,
    edit: str,
):
    """Replace the current path w/ the new path, either entirely, or if only partially if a
    continuation of dot(s) followed by some new path segment(s) is provided.  For example, if the
    default path for your desired format is:

        m/49'/0'/0'/0/0

    you can provide "../1/9" to produce "m/49'/0'/0'/1/9", or "...3" to produce "m/49'/0'/0'/0/3".

    To simply eliminate a segment, leave its segment empty.  For example, if you wish to eliminate
    the last two segments, provide "..//", yielding "m/49'/0'/0'".

    """
    if edit.startswith( '.' ):
        if ( new_edit := edit.lstrip( '.' )).startswith( '/' ):
            new_edit	= new_edit[1:]
        new_segs	= new_edit.split( '/' )
        cur_segs	= path.split( '/' )
        log.debug( f"Using {edit} to replace last {len(new_segs)} of {path} with {'/'.join(new_segs)}" )
        if len( new_segs ) >= len( cur_segs ):
            raise ValueError( f"Cannot use {edit} to replace last {len(new_segs)} of {path} with {'/'.join(new_segs)}" )
        # Truncate the number of edited segs, and appends only non-empty segments (effectively drops
        # any empty edited segments)
        res_segs	= cur_segs[:len(cur_segs)-len(new_segs)] + list(filter(None, new_segs))
        return '/'.join( res_segs )
    else:
        return edit


class BinanceMainnet( cryptocurrencies.Cryptocurrency ):
    NAME = "Binance"
    SYMBOL = "BSC"
    NETWORK = "mainnet"
    SOURCE_CODE = "https://github.com/bnb-chain/bsc"
    COIN_TYPE = cryptocurrencies.CoinType({
        "INDEX": 60,
        "HARDENED": True
    })

    SCRIPT_ADDRESS = 0x05
    PUBLIC_KEY_ADDRESS = 0x00
    SEGWIT_ADDRESS = cryptocurrencies.SegwitAddress({
        "HRP": "bc",
        "VERSION": 0x00
    })

    EXTENDED_PRIVATE_KEY = cryptocurrencies.ExtendedPrivateKey({
        "P2PKH": 0x0488ade4,
        "P2SH": 0x0488ade4,
        "P2WPKH": 0x04b2430c,
        "P2WPKH_IN_P2SH": 0x049d7878,
        "P2WSH": 0x02aa7a99,
        "P2WSH_IN_P2SH": 0x0295b005
    })
    EXTENDED_PUBLIC_KEY = cryptocurrencies.ExtendedPublicKey({
        "P2PKH": 0x0488b21e,
        "P2SH": 0x0488b21e,
        "P2WPKH": 0x04b24746,
        "P2WPKH_IN_P2SH": 0x049d7cb2,
        "P2WSH": 0x02aa7ed3,
        "P2WSH_IN_P2SH": 0x0295b43f
    })

    MESSAGE_PREFIX = None
    DEFAULT_PATH = f"m/44'/{str(COIN_TYPE)}/0'/0/0"
    WIF_SECRET_KEY = 0x80


class Account:
    """A Cryptocurrency "Account" / Wallet, based on a variety of underlying Python crypto-asset
    support modules.  Presently, only meherett/python-hdwallet is used.

    An appropriate hdwallet-like wrapper is built, for any crypto-asset supported using another
    module.  The required hdwallet API calls are:

      .from_seed	-- start deriving from the provided seed
      .from_mnemonic	-- start deriving from the provided seed via BIP-39/SLIP-39 mnemonic
      .clean_derivation	-- forget any prior derivation path
      .from_path	-- derive a wallet from the specified derivation path
      .p2pkh_address	-- produce a Legacy format address
      .p2sh_address	-- produce a SegWit format address
      .p2wpkh_address	-- produce a Bech32 format address
      .path		-- return the current wallet derivation path
      .private_key	-- return the current wallet's private key

    For testing eg. BIP-38 encrypted wallets:

      .from_private_key	-- import a specific private key
      .from_encrypted	-- import an encrypted wallet

    Also expect the following attributes to be available:

      ._cryptocurrency.SYMBOL:	The short name of the crypto-asset, eg 'XRP'

    Supports producing Legacy addresses for Bitcoin, and Litecoin.  Doge (D...) and Ethereum (0x...)
    addresses use standard BIP44 derivation.

    | Crypto | Semantic | Path              | Address | Support |
    |--------+----------+-------------------+---------+---------|
    | ETH    | Legacy   | m/44'/ 60'/0'/0/0 | 0x...   |         |
    | BSC    | Legacy   | m/44'/ 60'/0'/0/0 | 0x...   | Beta    |
    | BTC    | Legacy   | m/44'/  0'/0'/0/0 | 1...    |         |
    |        | SegWit   | m/49'/  0'/0'/0/0 | 3...    |         |
    |        | Bech32   | m/84'/  0'/0'/0/0 | bc1...  |         |
    | LTC    | Legacy   | m/44'/  2'/0'/0/0 | L...    |         |
    |        | SegWit   | m/49'/  2'/0'/0/0 | M...    |         |
    |        | Bech32   | m/84'/  2'/0'/0/0 | ltc1... |         |
    | DOGE   | Legacy   | m/44'/  3'/0'/0/0 | D...    |         |
    | XRP    | Legacy   | m/44'/144'/0'/0/0 | r...    | Beta    |

    """
    CRYPTO_SYMBOLS		= dict(
        # Convert known Symbols to official Cryptocurrency Name.  By convention, Symbols are
        # capitalized to avoid collisions with names
        ETH		= 'Ethereum',
        BTC		= 'Bitcoin',
        LTC		= 'Litecoin',
        DOGE		= 'Dogecoin',
        BSC		= 'Binance',
        XRP		= 'Ripple',
    )
    CRYPTO_DECIMALS		= dict(
        # Ethereum-related Cryptocurrencies are denominated 10^18, typically default 6 decimals
        # precision.  Bitcoin-related cryptocurrencies are typically 8 decimals precision (1 Sat is
        # 1/10^8 Bitcoin).  For XRP 1 Drop = 1/10^6 Ripple: https://xrpl.org/currency-formats.html
        # For formatting, we'll typically default to decimals//3, which works out fairly well for
        # most Cryptocurrencies and ERC-20 Tokens.  The exception are eg. WBTC (8 decimals) vs. BTC
        # (24 decimals); using the default 8 // 3 = 2 for WBTC would be dramatically too few
        # decimals of precision for practical use.  So, we recommend defaulting to the underlying
        # known cryptocurrency, when a proxy Token is used for price calculations.
        ETH		= 18,
        BTC		= 24,
        LTC		= 24,
        DOGE		= 24,
        BSC		= 18,
        XRP		= 6,
    )
    CRYPTO_NAMES		= dict(
        # Currently supported (in order of visibility), and conversion of known Names to Symbol.  By
        # convention, Cryptocurrency names are lower-cased to avoid collisions with symbols.
        ethereum	= 'ETH',
        bitcoin		= 'BTC',
        litecoin	= 'LTC',
        dogecoin	= 'DOGE',
        binance		= 'BSC',
        ripple		= 'XRP',
    )
    CRYPTOCURRENCIES		= set( CRYPTO_NAMES.values() )
    CRYPTOCURRENCIES_BETA	= set( ('BSC', 'XRP') )

    ETHJS_ENCRYPT		= set( ('ETH', 'BSC') )			# Can be encrypted w/ Ethereum JSON wallet
    BIP38_ENCRYPT		= CRYPTOCURRENCIES - ETHJS_ENCRYPT      # Can be encrypted w/ BIP-38

    CRYPTO_FORMAT		= dict(
        ETH		= "legacy",
        BTC		= "bech32",
        LTC		= "bech32",
        DOGE		= "legacy",
        BSC		= "legacy",
        XRP		= "legacy",
    )

    # Any locally-defined python-hdwallet classes, cryptocurrency definitions, and any that may
    # require some adjustments when calling python-hdwallet address and other functions.
    CRYPTO_WALLET_CLS		= dict(
    )
    CRYPTO_LOCAL		= dict(
        BSC		= BinanceMainnet,
    )
    CRYPTO_LOCAL_SYMBOL		= dict(
        BSC		= "ETH"
    )

    # The available address formats and default derivation paths.
    FORMATS		= ("legacy", "segwit", "bech32")

    CRYPTO_FORMAT_PATH		= dict(
        ETH		= dict(
            legacy	= "m/44'/60'/0'/0/0",
        ),
        BSC		= dict(
            legacy	= "m/44'/60'/0'/0/0",
        ),
        BTC		= dict(
            legacy	= "m/44'/0'/0'/0/0",
            segwit	= "m/49'/0'/0'/0/0",
            bech32	= "m/84'/0'/0'/0/0",
        ),
        LTC		= dict(
            legacy	= "m/44'/2'/0'/0/0",
            segwit	= "m/49'/2'/0'/0/0",
            bech32	= "m/84'/2'/0'/0/0",
        ),
        DOGE		= dict(
            legacy	= "m/44'/3'/0'/0/0",
        ),
        XRP		= dict(
            legacy	= "m/44'/144'/0'/0/0",
        )
    )

    CRYPTO_FORMAT_SEMANTIC	= dict(
        ETH		= dict(
            legacy	= "p2pkh",
        ),
        BSC		= dict(
            legacy	= "p2pkh",
        ),
        BTC		= dict(
            legacy	= "p2pkh",
            segwit	= "p2wpkh_in_p2sh",
            bech32	= "p2wpkh",
        ),
        LTC		= dict(
            legacy	= "p2pkh",
            segwit	= "p2wpkh_in_p2sh",
            bech32	= "p2wpkh",
        ),
        DOGE		= dict(
            legacy	= "p2pkh",
        ),
        XRP		= dict(
            legacy	= "p2pkh",
        )
    )

    @classmethod
    def path_default( cls, crypto, format=None ):
        """Return the default derivation path for the given crypto, based on its currently selected default
        address format.

        """
        crypto			= cls.supported( crypto )
        format			= format.lower() if format else cls.address_format( crypto )
        if format not in cls.CRYPTO_FORMAT_PATH[crypto]:
            raise ValueError( f"{format} not supported for {crypto}; specify one of {commas( cls.CRYPTO_FORMAT_PATH[crypto].keys() )}" )
        return cls.CRYPTO_FORMAT_PATH[crypto][format]

    @classmethod
    def address_format( cls, crypto, format=None ):
        """Get or set the desired default address format for the specified supported crypto.  Future
        instances of Address created for the crypto will use the specified address format and its
        default derivation path.

        """
        crypto			= cls.supported( crypto )
        if format is None:
            return cls.CRYPTO_FORMAT[crypto]

        format			= format.lower() if format else None
        if format not in cls.FORMATS:
            raise ValueError( f"{crypto} address format {format!r} not recognized; specify one of {commas( cls.FORMATS )}" )
        cls.CRYPTO_FORMAT[crypto]	= format

    @classmethod
    def supported( cls, crypto ):
        """Validates that the specified cryptocurrency is supported and returns the normalized "SYMBOL"
        for it, or raises an a ValueError.  Eg. "ETH"/"Ethereum" --> "ETH"

        """
        try:
            validated		= cls.CRYPTO_NAMES.get(
                crypto.lower(),
                crypto.upper() if crypto.upper() in cls.CRYPTO_SYMBOLS else None
            )
            if validated:
                return validated
        except Exception as exc:
            validated		= exc
            raise
        finally:
            log.debug( f"Validating {crypto!r} yields: {validated!r}" )

        raise ValueError( f"{crypto} not presently supported; specify {commas( cls.CRYPTOCURRENCIES )}" )

    def __str__( self ):
        """Until from_seed/from_path are invoked, may not have an address or derivation path."""
        address			= None
        try:
            address		= self.address
        except Exception:
            pass
        return f"{self.crypto}: {address}"

    def __repr__( self ):
        return f"{self.__class__.__name__}({self} @{self.path})"

    def __init__( self, crypto, format=None ):
        crypto			= Account.supported( crypto )
        cryptocurrency		= self.CRYPTO_LOCAL.get( crypto )
        self.format		= format.lower() if format else Account.address_format( crypto )
        semantic		= self.CRYPTO_FORMAT_SEMANTIC[crypto][self.format]
        hdwallet_cls		= self.CRYPTO_WALLET_CLS.get( crypto, hdwallet.HDWallet )
        if hdwallet_cls is None:
            raise ValueError( f"{crypto} does not support address format {self.format}" )
        self.hdwallet		= hdwallet_cls( symbol=crypto, cryptocurrency=cryptocurrency, semantic=semantic )

    def from_seed( self, seed: Union[str,bytes], path: Optional[str] = None, format=None ) -> Account:
        """Derive the Account from the supplied seed and (optionally) path; uses the default derivation
        path for the Account address format, if None provided.  As with all of the functions that
        completely replace the derivation Seed, we clear any existing known derivation path; it is
        unrelated to this newly supplied seed.  Handles bytes or hex seeds, optionally with "0x...".

        """
        if type( seed ) is bytes:
            seed		= codecs.encode( seed, 'hex_codec' ).decode( 'ascii' )
        if seed[:2].lower() == "0x":
            seed		= seed[2:]
        assert all( c in string.hexdigits for c in seed ), \
            "Only bytes and hex string HD Wallet Seeds are supported"

        self.hdwallet.clean_derivation()
        self.hdwallet.from_seed( seed )
        self.from_path( path )
        return self

    def from_mnemonic( self, mnemonic: str, path: Optional[str] = None, passphrase: Optional[Union[bytes,str]] = None, using_bip39: bool = False ) -> Account:
        """Derive the Account seed from the supplied BIP-39/SLIP-39 Mnemonic(s) and (optionally) path.
        Since Mnemonics are intended to encode "root" HD Wallet seeds, uses the default derivation
        path for the Account address format, if None provided.

        SLIP-39 Mnemonics are recognized by the fact that they are multiple lines (has newlines).

        If 'using_bip39', then any supplied SLIP-39 Mnemonics entropy will first be converted back
        into a BIP-39 Mnemonic (to maintain compatibility w/ BIP-39 wallets) to obtain the Seed.
        Otherwise, SLIP-39 Mnemonics will use native SLIP-39 Seed decoding.

        """
        mnemonics_lines		= [
            s.strip()
            for s in mnemonic.split( '\n' )
            if s.strip()
        ]
        if len( mnemonics_lines ) < 1:
            raise ValueError( "At least one BIP-39 2 SLIP-39 Mnemonics required" )
        if len( mnemonics_lines ) > 1:
            # Must be SLIP-39 Mnemonic Phrases
            seed		= recover_slip39( mnemonics_lines, passphrase=passphrase, using_bip39=using_bip39 )
            return self.from_seed( seed=seed, path=path )
        # Must be a single BIP-39 Mnemonic Phrase (as a UTF-8 string)
        if isinstance( passphrase, bytes ):
            passphrase		= passphrase.decode( 'UTF-8' )

        self.hdwallet.clean_derivation()
        self.hdwallet.from_mnemonic( *mnemonics_lines, passphrase=passphrase )  # python-hdwallet requires str/None
        self.from_path( path )
        return self

    def from_xpubkey( self, xpubkey: str, path: Optional[str] = None ) -> Account:
        """Derive the Account from the supplied xpubkey and (optionally) path; uses no derivation path
        by default derivation path for the Account address format, if None provided.

        Since this xpubkey may have been generated at some arbitrary path, eg.

            m/44'/60'/0'

        any subsequent path provided here, such as "m/0/0" will be "added" to the original
        derivation path, to give us the address at effective path eg.:

            m/44'/60'/0'/0/0

        However, if we ask for the self.path from this account, it will return only the portion
        provided here:

            m/0/0

        It is impossible to correctly recover any "hardened" accounts from an xpubkey, such as
        "m/1'/0".  These would need access to the private key material, which is missing.
        Therefore, the original account (or an xprivkey) would be required to access the desired
        path:

            m/44'/60'/0'/1'/0

        """
        self.hdwallet.clean_derivation()
        self.hdwallet.from_xpublic_key( xpubkey )
        self.from_path( path or "m/" )
        return self

    def from_xprvkey( self, xprvkey: str, path: Optional[str] = None ) -> Account:
        self.hdwallet.clean_derivation()
        self.hdwallet.from_xprivate_key( xprvkey )
        self.from_path( path or "m/" )
        return self

    def from_public_key( self, public_key: str, path: Optional[str] = None ) -> Account:
        self.hdwallet.clean_derivation()
        self.hdwallet.from_public_key( public_key )
        self.from_path( path or "m/" )
        return self

    def from_private_key( self, private_key: str, path: Optional[str] = None ) -> Account:
        self.hdwallet.clean_derivation()
        self.hdwallet.from_private_key( private_key )
        self.from_path( path or "m/" )
        return self

    def from_path( self, path: Optional[str] = None ) -> Account:
        """Change the Account to derive from the provided path (or from the default path, if currently
        empty, ie. 'm/').

        If a partial path is provided (eg "...1'/0/3"), then use it to replace the given segments in
        current (or the default) account path, leaving the remainder alone.

        If the derivation path is empty (only "m/") then leave the Account at clean_derivation state

        """
        from_path		= self.path
        log.debug( f"Changing {self.format} {self!r} from {from_path} to {path}" )
        if not from_path or len( from_path ) <= 2:
            if from_path != "m/":
                raise ValueError( f"Empty but invalid path detected: {from_path}" )
            log.debug( f"Default path for {self}, was {from_path!r}" )
            from_path		= Account.path_default( self.crypto, self.format )
        if path:
            into_path		= path_edit( from_path, path )
            log.debug( f"Editing path for {self}, from {from_path!r} w/ {path!r}, into {into_path!r}" )
            from_path		= into_path
        # Valid HD wallet derivation paths always start with "m/"
        if not ( from_path and len( from_path ) >= 2 and from_path.startswith( "m/" ) ):
            raise ValueError( f"Unrecognized HD wallet derivation path: {from_path!r}" )
        if len( from_path ) > 2:
            self.hdwallet.from_path( from_path )
        return self

    @property
    def address( self ):
        """Returns the 1..., 3... or bc1... address, depending on whether format is legacy, segwit or bech32"""
        return self.formatted_address()

    def formatted_address( self, format=None ):
        if ( format or self.format or '' ).lower() == "legacy":
            return self.legacy_address()
        elif ( format or self.format or '' ).lower() == "segwit":
            return self.segwit_address()
        elif ( format or self.format or '' ).lower() == "bech32":
            return self.bech32_address()
        raise ValueError( f"Unknown addresses semantic: {self.format}" )

    def substitute_symbol( method ):
        """For some locally-defined cryptocurrencies, the python-hdwallet code specifically checks
        for "ETH" and represents the address in the standard Ethereum 0x... format.  For those
        cryptocurrencies that need the underlying hdwallet._cryptocurrency.symbol adjusted during
        the call, place the entry in the CRYPTO_LOCAL_SYMBOL dict, above.

        Decorate the target methods that require the underlying .hdwallet._cryptocurrency.SYMBOL to
        be adjusted for the duration of the method.

        See: python-hdwallet/hdwallet/hdwallet.py, line 1102.

        """
        @wraps( method )
        def wrapper( self, *args, **kwds ):
            symbol              = self.hdwallet._cryptocurrency.SYMBOL
            try:
                self.hdwallet._cryptocurrency.SYMBOL \
                                = self.CRYPTO_LOCAL_SYMBOL.get( symbol, symbol )        # noqa: E126
                return method( self, *args, **kwds )
            finally:
                self.hdwallet._cryptocurrency.SYMBOL \
                                = symbol						# noqa: E126
        return wrapper

    @substitute_symbol
    def legacy_address( self ):
        """BIP-44 Address"""
        return self.hdwallet.p2pkh_address()

    def segwit_address( self ):
        """BIP-49 Address"""
        return self.hdwallet.p2wpkh_in_p2sh_address()

    def bech32_address( self ):
        """BIP-84 Address"""
        return self.hdwallet.p2wpkh_address()

    @property
    def name( self ):
        return self.hdwallet._cryptocurrency.NAME

    @property
    def symbol( self ):
        return self.hdwallet._cryptocurrency.SYMBOL
    crypto		= symbol

    @property
    def path( self ) -> str:
        return self.hdwallet.path() or 'm/'

    @property
    def key( self ):
        return self.hdwallet.private_key()
    prvkey		= key

    @property
    def xkey( self ):
        return self.hdwallet.xprivate_key()
    xprvkey		= xkey

    @property
    def pubkey( self ):
        return self.hdwallet.public_key()

    @property
    def xpubkey( self ):
        """Returns the xpub, ypub or zpub, depending on whether format is legacy, segwit or bech32.
        The HD wallet account represented by this xpub... key is that of the current derivation
        path, eg. "m/44'/60'/0'/0/0" for the default ETH wallet.  Thus, when restoring using
        eg. from_xpubkey, the default path used should be empty, ie. "m/".

        """
        return self.hdwallet.xpublic_key()

    def encrypted( self, passphrase ):
        """Output the appropriately encrypted private key for this cryptocurrency.  Ethereum uses
        encrypted JSON wallet standard, Bitcoin et.al. use BIP-38 encrypted private keys.

        A BIP-39 encrypted wallet encodes the private key at a certain derivation path, which is not
        remembered in the BIP-39 encoding!  Therefore, when you recover a BIP-39 encrypted wallet,
        you must tell the Account what derivation path you want to derive.  The default for None is
        NO derivation path (ie. "m/") -- the exact same wallet at whatever the derivation path was
        when .encrypted was invoked, is what will be recovered.

        """
        if self.crypto in self.ETHJS_ENCRYPT:
            if not eth_account:
                raise NotImplementedError( "The eth-account module is required to support Ethereum JSON wallet encryption; pip install slip39[wallet]" )
            wallet_dict		= eth_account.Account.encrypt( self.key, passphrase )
            return json.dumps( wallet_dict, separators=(',',':') )
        return self.bip38( passphrase )

    def from_encrypted( self, encrypted_privkey, passphrase, strict=True, path: Optional[str] = None ):
        """Import the appropriately decrypted private key for this cryptocurrency."""
        if self.crypto in self.ETHJS_ENCRYPT:
            if not eth_account:
                raise NotImplementedError( "The eth-account module is required to support Ethereum JSON wallet decryption; pip install slip39[wallet]" )
            private_hex		= bytes( eth_account.Account.decrypt( encrypted_privkey, passphrase )).hex()
            self.from_private_key( private_hex, path=path )
            return self
        return self.from_bip38( encrypted_privkey, passphrase=passphrase, strict=strict )

    def bip38( self, passphrase, flagbyte=b'\xe0' ):
        """BIP-38 encrypt the private key"""
        if not scrypt or not AES:
            raise NotImplementedError( "The scrypt module is required to support BIP-38 encryption; pip install slip39[wallet]" )
        if self.crypto not in self.BIP38_ENCRYPT:
            raise NotImplementedError( f"{self.crypto} does not support BIP-38 private key encryption" )
        private_hex		= self.key
        addr			= self.legacy_address().encode( 'UTF-8' )  # Eg. b"184xW5g..."
        ahash			= hashlib.sha256( hashlib.sha256( addr ).digest() ).digest()[0:4]
        if isinstance( passphrase, str ):
            passphrase		= passphrase.encode( 'UTF-8' )
        key			= scrypt( passphrase or b"", salt=ahash, key_len=64, N=16384, r=8, p=8 )
        derivedhalf1		= key[0:32]
        derivedhalf2		= key[32:64]
        aes			= AES.new( derivedhalf2, AES.MODE_ECB )
        enchalf1		= aes.encrypt( ( int( private_hex[ 0:32], 16 ) ^ int.from_bytes( derivedhalf1[ 0:16], 'big' )).to_bytes( 16, 'big' ))
        enchalf2		= aes.encrypt( ( int( private_hex[32:64], 16 ) ^ int.from_bytes( derivedhalf1[16:32], 'big' )).to_bytes( 16, 'big' ))
        prefix			= b'\x01\x42'
        encrypted_privkey	= prefix + flagbyte + ahash + enchalf1 + enchalf2
        # Encode the encrypted private key to base58, adding the 4-byte base58 check suffix
        return base58.b58encode_check( encrypted_privkey ).decode( 'UTF-8' )

    def from_bip38( self, encrypted_privkey, passphrase, path: Optional[str] = None, strict: bool = True ):
        """Bip-38 decrypt and import the private key."""
        if not scrypt or not AES:
            raise NotImplementedError( "The scrypt module is required to support BIP-38 decryption; pip install slip39[wallet]" )
        if self.crypto not in self.BIP38_ENCRYPT:
            raise NotImplementedError( f"{self.crypto} does not support BIP-38 private key decryption" )
        # Decode the encrypted private key from base58, discarding the 4-byte base58 check suffix
        d			= base58.b58decode_check( encrypted_privkey )
        assert len( d ) == 43 - 4, \
            f"BIP-38 encrypted key should be 43 bytes long, not {len( d ) + 4} bytes"
        pre,flag,ahash,eh1,eh2	= d[0:2],d[2:3],d[3:7],d[7:7+16],d[7+16:7+32]
        assert pre == b'\x01\x42', \
            f"Unrecognized BIP-38 encryption prefix: {pre!r}"
        assert flag in ( b'\xc0', b'\xe0' ), \
            f"Unrecognized BIP-38 flagbyte: {flag!r}"
        if isinstance( passphrase, str ):
            passphrase		= passphrase.encode( 'UTF-8' )
        key			= scrypt( passphrase or b"", salt=ahash, key_len=64, N=16384, r=8, p=8 )
        derivedhalf1		= key[0:32]
        derivedhalf2		= key[32:64]
        aes			= AES.new( derivedhalf2, AES.MODE_ECB )
        dechalf2		= aes.decrypt( eh2 )
        dechalf1		= aes.decrypt( eh1 )
        priv			= dechalf1 + dechalf2
        priv			= ( int.from_bytes( priv, 'big' ) ^ int.from_bytes( derivedhalf1, 'big' )).to_bytes( 32, 'big' )
        # OK, we have the Private Key; we can recover the account, then verify the
        # remainder of the checks
        private_hex		= codecs.encode( priv, 'hex_codec' ).decode( 'ascii' )
        self.from_private_key( private_hex, path=path )
        addr			= self.legacy_address().encode( 'UTF-8' )  # Eg. b"184xW5g..."
        ahash_confirm		= hashlib.sha256( hashlib.sha256( addr ).digest() ).digest()[0:4]
        if ahash_confirm != ahash:
            warning		= f"BIP-38 address hash verification failed ({ahash_confirm.hex()} != {ahash.hex()}); passphrase may be incorrect."
            if strict:
                raise AssertionError( warning )
            else:
                log.warning( warning )
        return self


def path_parser(
    paths: str,
    allow_unbounded: bool	= True,
) -> Tuple[str, Dict[str, Callable[[], int]]]:
    """Create a format and a dictionary of iterators to feed into it.

    Supports paths with an arbitrary prefix, eg. 'm/' or '../'
    """
    path_segs			= paths.split( '/' )
    unbounded			= False
    ranges			= {}

    for i,s in list( enumerate( path_segs )):
        if '-' not in s:
            continue
        c			= chr(ord('a')+i)
        tic			= s.endswith( "'" )
        if tic:
            s			= s[:-1]
        b,e			= s.split( '-' )
        b			= int( b or 0 )
        if e:
            e			= int( e )
            ranges[c]		= lambda b=b,e=e: range( b, e+1 )
        else:
            assert allow_unbounded and not ( unbounded or ranges ), \
                f"{'Only first' if allow_unbounded else 'No'} range allowed to be unbounded;" \
                f" this is the {ordinal(len(ranges)+1)} range in {paths}"
            unbounded		= True
            ranges[c]		= lambda b=b: itertools.count( b )
        path_segs[i]		= f"{{{c}}}" + ( "'" if tic else "" )

    path_fmt			= '/'.join( path_segs )
    return path_fmt, ranges


def path_sequence(
    path_fmt: str,
    ranges: Dict[str, Callable[[], int]],
):
    """Yield a sequence of paths, modulating the format specifiers of the
    path_fmt according to their value sources in ranges.

    For example, a

        path_fmt = "m/44'/60'/0'/0/{f}", with a
        ranges   = dict( f=lambda b=0, e=2: range( b, e+1 ) )

    would yield the paths:

        "m/44'/60'/0'/0/0"
        "m/44'/60'/0'/0/1"
        "m/44'/60'/0'/0/2"
    """
    # Stert all the iterators
    viters			= {
        k: iter( l() )
        for k,l in ranges.items()
    }
    values			= {		# Initial round of values; must provide at least one
        k: next( viters[k] )
        for k in viters
    }
    assert all( v is not None for v in values.values() ), \
        "Iterators for path segment values must yield at least an initial value"

    while not any( v is None for v in values.values() ):
        yield path_fmt.format( **values )
        if not ranges:
            break				# No variable records at all; just one
        # Get the next value.  Working from the lowest iterator up, cycle value(s)
        for i,k in enumerate( sorted( viters.keys(), reverse=True )):
            values[k]		= next( viters[k], None )
            if values[k] is not None:
                break
            # OK, this iterable has ended.  Restart it, and cycle to the next one up, iff
            # there are remaining ranges
            if i+1 < len( ranges ):
                viters[k]	= iter( ranges[k]() )
                values[k]	= next( viters[k], None )


def path_hardened( path ):
    """Remove any non-hardened components from the end of path, eg:

    >>> path_hardened( "m/84'/0'/0'/1/2" )
    ("m/84'/0'/0'", 'm/1/2')
    >>> path_hardened( "m/1" )
    ('m/', 'm/1')
    >>> path_hardened( "m/1'" )
    ("m/1'", 'm/')
    >>> path_hardened( "m/" )
    ('m/', 'm/')
    >>> path_hardened( "m/1/2/3'/4" )
    ("m/1/2/3'", 'm/4')

    Returns  the two components as a tuple of two paths
    """
    segs			= path.split( '/' )
    # Always leaves the m/ on the hard path
    for hardened in range( 1, len( segs ) + 1 ):
        if not any( "'" in s for s in segs[hardened:] ):
            break
    else:
        log.debug( f"No non-hardened path segments in {path}" )

    hard			= 'm/' + '/'.join( segs[1:hardened] )
    soft			= 'm/' + '/'.join( segs[hardened:] )
    return hard,soft


def cryptopaths_parser(
    cryptocurrency,  # Or a cryptopaths list, eg. ["XRP",(ETH,"m/.."),(BTC,NONE,"segwit")]
    edit			= None,
    hardened_defaults		= False,
    format			= None,
):
    """Generate a standard cryptopaths list, from the given sequnce of "<crypto>",
    (<crypto>,<paths>), (<crypto>,<paths>,<format>), or "<crypto>[:<paths>[:<format>:]"
    cryptocurrencies (default: CRYPTO_PATHS, optionally w/ only the hardened portion of the path,
    eg. omitting the trailing ../0/0).

    Adjusts the provided derivation paths by an optional eg. "../-" path adjustment.

    A non-default format may be specified, which may change the default HD derivation path.  This
    must also be passed back, as it also affects the crypto's account's address format.

    """
    for crypto in cryptocurrency or CRYPTO_PATHS:
        if type(crypto) is str:
            crypto		= crypto.split( ':' )

        cry,*pth		= crypto
        pth,*fmt		= pth or (None,)
        fmt,			= fmt or (format,)

        cry			= Account.supported( cry )
        if not pth:
            pth			= Account.path_default( cry, fmt )
            if hardened_defaults:
                pth,_		= path_hardened( pth )
        if edit:
            pth			= path_edit( pth, edit )
        yield (cry,pth,fmt)


def random_secret(
    seed_length: Optional[int]
) -> bytes:
    """Generates a new random secret.

    NOTE: There is a slightly less than 1 / 2^128 chance that any given random secret will lead to
    an invalid BTC wallet private key!  This is because the 256-bit seed for bitcoin must be less than
    the secp256k1 field size:

        0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

    We cannot generate secrets that are guaranteed to be valid for every derived HD Wallet BTC
    address.  The secret is derived through a complex hashing procedure for each wallet at each
    path.  The probability of this occurring is so vanishingly small that we will instead simply opt
    to *not* generate an public wallet address, when asked.

    Just to give you an understandable reference, the first 128 bits of an illegal secret unusable
    for generating a Bitcoin wallet must have 128 '1' bits at its start.  If wallets were generated
    at a billion per second, by every person alive on earth, it should take about 1.5 trillion years
    to arrive at the first invalid seed.

    2**128 / 1e9 / 7e9 / (60*60*24*365) == 1,541,469,010,115.145

    """
    assert seed_length, \
        f"Must supply a non-zero length in bytes, not {seed_length}"
    return RANDOM_BYTES( seed_length )


def stretch_seed_entropy( entropy, n, bits, encoding=None ):
    """To support the generation of a number of Seeds, each subsequent seed *must* be independent of
    the prior seed: thus, if a number of seeds are produced from the same entropy, it *must* extend
    beyond the amount used by the seed, so the additional entropy beyond the end of that used is
    stretched into the subsequent batch of 'bits' worth of entropy returned.  So, for 128-bit or
    256-bit seeds, supply entropy longer than this bit amount if more than one seed is to be
    enhanced using this entropy source.

    The Seed Data supplied (ie. recovered from BIP/SLIP-39 Mnemonics, or from fixed/random data) is
    of course unchanging for the subsequent seeds to be produced; only the "extra" Seed Entropy is
    useful for producing multiple sequential Seeds.  Returns the designated number of bits (rounded
    up to bytes).

    If non-binary hex data is supplied, encoding should be 'hex_codec' (0-filled/truncated on the
    right up to the required number of bits); otherwise probably 'UTF-8' (and we'll always stretch
    other encoded Entropy, even for the first (ie. 0th) seed).

    If binary data is supplied, it must be sufficient to provide the required number of bits for the
    first and subsequent Seeds (SHA-512 is used to stretch, so any encoded and stretched entropy
    data will be sufficient) for 128- and 256-bit seeds.

    """
    assert n == 0 or ( entropy and n >= 0 ), \
        f"Some Extra Seed Entropy is required to produce the {ordinal(n+1)}+ Seed(s)"
    assert ( type(entropy) is bytes ) == ( not encoding ), \
        "If non-binary Seed Entropy is supplied, an appropriate encoding must be specified"
    if encoding:
        if encoding == 'hex_codec':
            # Hexadecimal Entropy was provided; Use the raw encoded Hex data for the first round!
            entropy		= f"{entropy:<0{bits // 4}.{bits // 4}}"
            entropy		= codecs.decode( entropy, encoding )  # '012abc' --> b'\x01\x2a\xbc'
        else:
            # Other encoding was provided, eg 'UTF-8', 'ASCII', ...; stretch for the 0th Seed, too.
            n		       += 1
            entropy		= codecs.encode( entropy, encoding )    # '012abc' --> b'012abc'
    octets			= ( bits + 7 ) // 8
    if entropy:
        for _ in range( n ):
            entropy		= hashlib.sha512( entropy ).digest()
    else:
        # If no entropy provided, result is all 0
        entropy			= b'\0' * octets
    assert len( entropy ) >= octets, \
        "Insufficient extra Seed Entropy provided for {ordinal(n+1)} {bits}-bit Seed"
    return entropy[:octets]


Details = namedtuple( 'Details', ('name', 'group_threshold', 'groups', 'accounts', 'using_bip39') )


def enumerate_mnemonic( mnemonic ):
    """Return a dict containing the supplied mnemonics stored by their indexed, starting from 0.
    Each Mnemonic is labelled with its ordinal index (ie. beginning at 1).

    """
    if isinstance( mnemonic, str ):
        mnemonic		= mnemonic.split( ' ' )
    return dict(
        (i, f"{i+1:>2d} {w}")
        for i,w in enumerate( mnemonic )
    )


def organize_mnemonic( mnemonic, rows=None, cols=None, label="" ):
    """Given a SLIP-39 "word word ... word" or ["word", "word", ..., "word"] mnemonic, emit rows
    organized in the desired rows and cols (with defaults, if not provided).  We return the fully
    formatted line, plus the list of individual words in that line.

    """
    num_words			= enumerate_mnemonic( mnemonic )
    if not rows or not cols:
        rows,cols		= MNEM_ROWS_COLS.get( len(num_words), (7, 3))
    for r in range( rows ):
        line			= label if r == 0 else ' ' * len( label )
        words			= []
        for c in range( cols ):
            word		= num_words.get( c * rows + r )
            if word:
                words.append( word )
                line	       += f"{word:<13}"
        yield line,words


def group_parser( group_spec ):
    """Parse a SLIP-39 group specification.

        Frens6, Frens 6, Frens(6)	- A 3/6 group (default is 1/2 of group size, rounded up)
        Frens2/6, Frens(2/6)		- A 2/6 group

    """
    match			= group_parser.RE.match( group_spec )
    if not match:
        raise ValueError( f"Invalid group specification: {group_spec!r}" )
    name			= match.group( 'name' )
    size			= match.group( 'size' )
    require			= match.group( 'require' )
    if not size:
        size			= 1
    if not require:
        # eg. default 2/4, 3/5
        require			= math.ceil( int( size ) * GROUP_REQUIRED_RATIO )
    return name,(int(require),int(size))
group_parser.RE			= re.compile( # noqa E305
    r"""^
        \s*
        (?P<name> [^\d\(/]+ )
        \s*\(?\s*
        (?: (?P<require> \d* ) \s* / )?
        \s*
        (?P<size> \d* )
        \s*\)?\s*
        $""", re.VERBOSE )


def create(
    name: str,
    group_threshold: Optional[Union[int,float]] = None,		# Default: 1/2 of groups, rounded up
    groups: Optional[Union[List[str],Dict[str,Tuple[int, int]]]] = None,  # Default: 4 groups (see defaults.py)
    master_secret: Optional[Union[str,bytes]] = None,		# Default: generate 128-bit Seed Entropy
    passphrase: Optional[Union[bytes,str]] = None,
    using_bip39: Optional[bool]	= None,  # Produce wallet Seed from master_secret Entropy using BIP-39 generation
    iteration_exponent: int	= 1,
    cryptopaths: Optional[Sequence[Union[str,Tuple[str,str],Tuple[str,str,str]]]] = None,  # default: ETH, BTC at default path, format
    strength: Optional[int]	= None,				# Default: 128
    extendable: Optional[Union[bool,int]] = None,		# Default: True w/ random identifier
) -> Tuple[str,int,Dict[str,Tuple[int,List[str]]], Sequence[Sequence[Account]], bool]:
    """Creates a SLIP-39 encoding for supplied master_secret Entropy, and 1 or more Cryptocurrency
    accounts.  Returns the Details, in a form directly compatible with the layout.produce_pdf API.

    The master_secret Seed Entropy is discarded (because it is, of course, always recoverable from
    the SLIP-39 mnemonics).

    We strive to default to "do the right thing", here.  If you supply BIP-39 Mnemonics, we'll
    round-trip them via SLIP-39, and produce compatible crypto account addresses.  This should be
    the "typical" case, as most people already have BIP-39 Mnemonics.  If you don't have a BIP-39
    Mnemonic, make sure you set using_bip39 = True; this *also* implies that you *MUST* have already
    converted your entropy to BIP-39 (or are going to recover it and do so, later), so we'll warn
    you to do that.  If a passphrase is provided, it is assumed to be a BIP-39 passphrase, and is used
    to generate the crypto account addresses -- it will *not* be used to "encrypt" the SLIP-39!

    If you supply raw entropy, we'll assume you have SLIP-39 compatible wallet and want to use it
    directly.

    Creates accountgroups derived from the Seed Entropy.  By default, this is done in the SLIP-39
    standard, using the master_secret Entropy directly.  If a passphrase is supplied, this is also
    used in the SLIP-39 standard fashion (not recommended -- not Trezor compatible).

    If using_bip39, creates the Cryptocurrency accountgroups from the supplied master_secret
    Entropy, by generating the Seed from a BIP-38 Mnemonic produced from the provided entropy
    (or generated, default 128 bits), plus any supplied passphrase.

    """
    if master_secret is None:
        if not strength:
            strength		= BITS_DEFAULT
        master_secret		= random_secret( strength // 8 )
    if isinstance( master_secret, bytes ) and not ( 128 <= len( master_secret ) * 8 <= 512 ):
        log.warning( f"Strangely sized {len(master_secret) * 8}-bit entropy provided; may be weak" )

    # If a non-hex str is passed as entropy, assume it is a BIP-39 Mnemonic, and that we want to use
    # SLIP-39 to round-trip the underlying BIP-39 entropy AND derive compatible wallets.
    if isinstance( master_secret, str ) and all( c in '0123456789abcdef' for c in master_secret.lower() ):
        master_secret		= codecs.decode( master_secret, 'hex_codec' )
    if using_bip39 is None and isinstance( master_secret, str ):
        # Assume it must be a BIP-39 Mnemonic
        using_bip39		= True
    else:
        # Assume caller knows; default False (use SLIP-39 directly)
        using_bip39		= bool( using_bip39 )

    # Derive the desired account(s) at the specified derivation paths, or the default, using either
    # BIP-39 Seed generation, or directly from Entropy for SLIP-39.
    if using_bip39:
        # For BIP-39, the passphrase is consumed here, and Cryptocurrency accounts are generated
        # using the BIP-39 Seed generated from entropy + passphrase.  This should be the "typical"
        # use-case, where someone already has a BIP-39 Mnemonic and/or wants to use a "standard"
        # BIP-39 compatible hardware wallet.
        log.warning( "Assuming BIP-39 seed entropy: Ensure you recover and use via a BIP-39 Mnemonic" )
        if isinstance( master_secret, str ):
            master_secret	= recover_bip39( mnemonic=master_secret, as_entropy=True )
        bip39_mnem		= produce_bip39( entropy=master_secret )
        bip39_seed		= recover_bip39(
            mnemonic	= bip39_mnem,
            passphrase	= passphrase,
        )
        log.info(
            f"SLIP-39 for {name} from {len(master_secret)*8}-bit Entropy using BIP-39 Mnemonic{' w/ Passphrase' if passphrase else ''}"
        )
        accts			= list( accountgroups(
            master_secret	= bip39_seed,
            cryptopaths		= cryptopaths,
            allow_unbounded	= False,
        ))
        passphrase		= None  # Consumed by BIP-39; not used for SLIP-39 Mnemonics "backup"!
    else:
        # For SLIP-39, accounts are generated directly from supplied Entropy, and passphrase
        # encrypts the SLIP-39 Mnemonics, below.  Using a SLIP-39 with a passphrase is so unlikely
        # to be correct that we will warn about it!  You almost *always* want to use SLIP-39
        # *without* a passphase; use eg. Trezor "hidden wallets" instead.
        (log.warning if passphrase else log.info)(
            f"SLIP-39 for {name} from {len(master_secret)*8}-bit Entropy directly{' w/ SLIP-39 Passphrase' if passphrase else ''}"
        )
        accts			= list( accountgroups(
            master_secret	= master_secret,
            cryptopaths		= cryptopaths,
            allow_unbounded	= False,
        ))

    # Deduce groups, using defaults
    if not groups:
        groups			= GROUPS
    if not is_mapping( groups ):
        if isinstance( groups, str ):
            groups		= groups.split( "," )
        groups			= dict( map( group_parser, groups ))
    g_names,g_dims		= list( zip( *groups.items() ))

    # Generate the SLIP-39 Mnemonics representing the supplied master_secret Seed Entropy.  This
    # always recovers the Seed Entropy; if not using_bip39, this is also the wallet derivation Seed;
    # if using_bip39, the wallet derivation Seed was produced from the BIP-39 Seed generation
    # process (which consumes any passphrase, and the SLIP-39 passphrase is always None, here).
    mnems			= mnemonics(
        group_threshold	= group_threshold,
        groups		= g_dims,
        master_secret	= master_secret,
        passphrase	= passphrase,
        iteration_exponent= iteration_exponent,
        extendable	= extendable
    )

    groups			= {
        g_name: (g_of, g_mnems)
        for (g_name,(g_of, _),g_mnems) in zip( g_names, g_dims, mnems )
    }
    if log.isEnabledFor( logging.INFO ):
        group_reqs			= list(
            f"{g_nam}({g_of}/{len(g_mns)})" if g_of != len(g_mns) else f"{g_nam}({g_of})"
            for g_nam,(g_of,g_mns) in groups.items() )
        requires		= f"Recover w/ {group_threshold} of {len(groups)} groups {commas( group_reqs )}"
        for g_n,(g_name,(g_of,g_mnems)) in enumerate( groups.items() ):
            log.info( f"{g_name}({g_of}/{len(g_mnems)}): {'' if g_n else requires}" )
            for mn_n,mnem in enumerate( g_mnems ):
                for line,_ in organize_mnemonic( mnem, label=f"{ordinal(mn_n+1)} " ):
                    log.info( f"{line}" )

    return Details(name, group_threshold, groups, accts, using_bip39)


def mnemonics(
    group_threshold: Optional[int],  # Default: 1/2 of groups, rounded up
    groups: Sequence[Tuple[int, int]],
    master_secret: Optional[Union[bytes,EncryptedMasterSecret]] = None,
    passphrase: Optional[Union[bytes,str]] = None,
    iteration_exponent: int	= 1,
    strength: int		= BITS_DEFAULT,
    extendable: Optional[Tuple[bool,int]] = None,
) -> List[List[str]]:
    """Generate SLIP39 mnemonics for the supplied master_secret for group_threshold of the given
     groups.  Will generate a random master_secret, if necessary.

    If you have BIP-39/SLIP-39 Mnemonic(s), use recovery.recover or .recover_bip39 first.  To
    "backup" a BIP-39 Mnemonic Phrase, you probably want to use .recover_bip39( ..., as_entropy=True
    ) to get the original 128- or 256-bit Entropy, and then produce SLIP-39 Mnemonics from that.

    Later, supply these SLIP-39 Mnemonics to any of the .account... functions with using_bip39=True,
    to derive the original BIP-39 wallets.

    An encrypted master seed may be supplied, recovered from SLIP-39 mnemonics.  This allows the
    caller to convert an existing encrypted seed to produce another set of SLIP-39 Mnemonics.  If
    extendable, and the group_threshold, number of groups and group minimums are not changed, then
    the result will be an extension of an existing set of SLIP-39 Mnemonics.  Otherwise, it will be
    a new (but incompatible) set of Mnemonics.

    """
    if master_secret is None:
        master_secret		= random_secret(( strength + 7 ) // 8 )

    if isinstance( master_secret, EncryptedMasterSecret ):
        assert not passphrase, \
            "No passphrase required/allowed for encrypted master seed"
        encrypted_secret	= master_secret
    else:
        if passphrase is None:
            passphrase		= ""
        if isinstance( passphrase, str ):
            passphrase		= passphrase.encode( 'UTF-8' )
        encrypted_secret	= EncryptedMasterSecret.from_master_secret(
            master_secret = master_secret,
            passphrase	= passphrase,
            identifier	= _random_identifier() if extendable in (None, False, True) else extendable,
            extendable	= False if extendable is False else True,
            iteration_exponent = iteration_exponent,
        )

    if len( encrypted_secret.ciphertext ) * 8 not in BITS:
        raise ValueError(
            f"Only {commas( BITS, final='and' )}-bit seeds supported; {len(encrypted_secret.ciphertext)*8}-bit seed supplied" )

    return mnemonics_encrypted(
        group_threshold	= group_threshold,
        groups		= groups,
        encrypted_secret = encrypted_secret,
    )


def mnemonics_encrypted(
    group_threshold: Optional[int],
    groups: Sequence[Tuple[int, int]],
    encrypted_secret: EncryptedMasterSecret,
) -> List[List[str]]:
    """Generate SLIP-39 mnemonics for the supplied encrypted_secret.  To reliably generate mnemonics
    to extend existing encrypted SLIP-39 gruop(s), supply an EncryptedMasterSecret with an
    'extendable' SLIP-39 identifier.

    If the group threshold, count and group minimum requirements are consistent (just the group
    size(s) are increased), then the Mnemonics will be an extension of the existing group(s) --
    producing more potential recovery options for 1 or more group(s).  Since SLIP-39 doesn't allow
    "1 of X" groups (for anything other than "1 of 1"), you cannot extend existing "1 of 1" groups.

    """
    groups			= list( groups )
    if not group_threshold:
        group_threshold		= math.ceil( len( groups ) * GROUP_THRESHOLD_RATIO )

    grouped_shares		= split_ems( group_threshold, groups, encrypted_secret )
    log.warning(
        f"Generated {len(encrypted_secret.ciphertext)*8}-bit SLIP-39 Mnemonics w/ identifier {encrypted_secret.identifier} requiring {group_threshold}"
        f" of {len(grouped_shares)}{' (extendable)' if encrypted_secret.extendable else ''} groups to recover" )

    return [[share.mnemonic() for share in group] for group in grouped_shares]


def account(
    master_secret: Union[str,bytes],
    crypto: Optional[str]	= None,  # default 'ETH'
    path: Optional[str]		= None,  # default to the crypto's path_default
    format: Optional[str]	= None,  # eg. 'bech32', or use the default address format for the crypto
    passphrase: Optional[Union[bytes,str]] = None,  # If mnemonic(s) provided, then passphrase/using_bip39 optional
    using_bip39: bool		= False,
):
    """Generate an HD wallet Account from the supplied master_secret seed, at the given HD derivation
    path, for the specified cryptocurrency.

    If the master_secret is bytes, it is used as-is.  If a str, then we generally expect it to be
    hex.  However, this is where we can detect alternatives like "{x,y,z}{pub,priv}key...".  These
    are identifiable by their prefix, which is incompatible with hex, so there is no ambiguity.

    """
    if isinstance( master_secret, str ):
        master_secret		= master_secret.strip()
    if isinstance( master_secret, bytes ) or master_secret[:2].lower == "0x" or all(
        c in string.hexdigits for c in master_secret
    ):
        # Probably a binary/hex Seed.
        acct			= Account(
            crypto	= crypto or 'ETH',
            format	= format,
        )
        acct.from_seed(
            seed	= master_secret,
            path	= path,
        )
        log.debug( f"Created {acct.format} {acct} from {len(master_secret)*8}-bit seed, at derivation path {acct.path}" )
    elif ' ' in master_secret:
        # Some kind of Mnemonic; this is the only valid use of whitespace within a master_secret.
        acct			= Account(
            crypto	= crypto or 'ETH',
            format	= format,
        )
        log.debug( f"Making  {acct.format} {acct} from Mnemonic(s), at derivation path {acct.path}" )
        acct.from_mnemonic( master_secret, path=path, passphrase=passphrase, using_bip39=using_bip39 )
        log.debug( f"Created {acct.format} {acct} from Mnemonic(s), at derivation path {acct.path}" )
    else:
        # See if we recognize the prefix as a {x,y,z}pub... or .prv...  Get the bound function for
        # initializing the seed.  Also, deduce the default format from the x/y/z+pub/prv.
        default_fmt,from_method	= {
            'xpub': ('legacy', Account.from_xpubkey),
            'xprv': ('legacy', Account.from_xprvkey),
            'ypub': ('segwit', Account.from_xpubkey),
            'yprv': ('segwit', Account.from_xprvkey),
            'zpub': ('bech32', Account.from_xpubkey),
            'zprv': ('bech32', Account.from_xprvkey),
        }.get( master_secret[:4], (None,None) )
        if from_method is None:
            raise ValueError(
                f"Only x/y/z + pub/prv prefixes supported; {master_secret[:8]+'...'!r} prefix supplied" )
        if format is None:
            format		= default_fmt
        acct			= Account(
            crypto	= crypto or 'ETH',
            format	= format
        )
        from_method( acct, master_secret, path )  # It's an unbound method, so pass the instance
        log.debug( f"Created {acct.format} {acct} from {master_secret[:4]} key, at derivation path {acct.path}" )

    return acct


def accounts(
    master_secret: Union[str,bytes],
    crypto: str			= None,  # default 'ETH'
    paths: str			= None,  # default to the crypto's path_default; allow ranges
    format: Optional[str]	= None,
    allow_unbounded		= True,
    passphrase: Optional[Union[bytes,str]] = None,  # If mnemonic(s) provided, then passphrase/using_bip39 optional
    using_bip39: bool		= False,
):
    """Create accounts for crypto, at the provided paths (allowing ranges), with the optionsal address format. """
    for path in [None] if paths is None else path_sequence( *path_parser(
        paths		= paths,
        allow_unbounded	= allow_unbounded,
    )):
        yield account(
            master_secret,
            crypto	= crypto,
            path	= path,
            format	= format,
            passphrase	= passphrase,
            using_bip39	= using_bip39,
        )


def accountgroups(
    master_secret: Union[str,bytes],
    cryptopaths: Optional[Sequence[Union[str,Tuple[str,str],Tuple[str,str,str]]]] = None,  # default: ETH, BTC at default path, format
    allow_unbounded: bool	= True,
    passphrase: Optional[Union[bytes,str]] = None,      # If mnemonic(s) provided, then passphrase/using_bip39 optional
    using_bip39: bool		= False,
    format: Optional[str]	= None,			# If the default format for every cryptopath isn't desired
    edit: Optional[str]		= None,
    hardened_defaults: bool	= False,
) -> Sequence[Sequence[Account]]:
    """Generate the desired cryptocurrency account(s) at each crypto's given path(s).  This is useful
    for generating sequences of groups of wallets for multiple cryptocurrencies, eg. for receiving
    multiple cryptocurrencies for each client.  Since each cryptocurrency uses a different BIP-44 path,
    we have to generate different sequences.

    Supports ranges in each path segment, eg.:

        ('ETH', "m/44'/60'/0'/0/-")	-- generates all accounts for ETH
        ('BTC', "m/44'/0'/0'/0/-")	-- generates all accounts for BTC

        [
          [ "m/44'/60'/0'/0/0", "0x824b174803e688dE39aF5B3D7Cd39bE6515A19a1"],
          [ "m/44'/0'/0'/0/0", "1MAjc529bjmkC1iCXTw2XMHL2zof5StqdQ"]
        ],
        [
          [ "m/44'/60'/0'/0/1", "0x8D342083549C635C0494d3c77567860ee7456963"],
          [ "m/44'/0'/0'/0/1", "1BGwDuVPJeXDG9upaHvVPds5MXwkTjZoav"]
        ],
        ...

    """
    yield from zip( *[
        accounts(
            master_secret	= master_secret,
            crypto		= cry,
            paths		= pth,
            format		= fmt,
            allow_unbounded	= allow_unbounded,
            passphrase		= passphrase,
            using_bip39		= using_bip39,
        )
        for cry,pth,fmt in cryptopaths_parser(
            cryptopaths,
            edit		= edit,
            hardened_defaults	= hardened_defaults,
            format		= format,
        )
    ])


def address(
    master_secret: Union[str,bytes],
    crypto: str			= None,
    path: str			= None,
    format: Optional[str]	= None,
    passphrase: Optional[Union[bytes,str]] = None,  # If mnemonic(s) provided, then passphrase/using_bip39 optional
    using_bip39: bool		= False,
):
    """Return the specified cryptocurrency HD account address at path."""
    return account(
        master_secret,
        path		= path,
        crypto		= crypto,
        format		= format,
        passphrase	= passphrase,
        using_bip39	= using_bip39,
    ).address


def addresses(
    master_secret: Union[str,bytes],
    crypto: str	 		= None,  # default 'ETH'
    paths: str			= None,  # default: The crypto's path_default; supports ranges
    format: Optional[str]	= None,
    allow_unbounded: bool	= True,
    passphrase: Optional[Union[bytes,str]] = None,  # If mnemonic(s) provided, then passphrase/using_bip39 optional
    using_bip39: bool		= False,
):
    """Generate a sequence of cryptocurrency account (path, address, ...)  for all designated
    cryptocurrencies.  Usually a single (<path>, <address>) tuple is desired (different
    cryptocurrencies typically have their own unique path derivations.

    """
    for acct in accounts(
            master_secret,
            crypto	= crypto,
            paths	= paths,
            format	= format,
            allow_unbounded = allow_unbounded,
            passphrase	= passphrase,
            using_bip39	= using_bip39,
    ):
        yield (acct.crypto, acct.path, acct.address)


def addressgroups(
    master_secret: Union[str,bytes],
    cryptopaths: Optional[Sequence[Union[str,Tuple[str,str],Tuple[str,str,str]]]] = None,  # default: ETH, BTC at default path, format
    allow_unbounded: bool	= True,
    passphrase: Optional[Union[bytes,str]] = None,  # If mnemonic(s) provided, then passphrase/using_bip39 optional
    using_bip39: bool		= False,
    format: Optional[str]	= None,
    edit: Optional[str]		= None,
    hardened_defaults: bool	= False,
) -> Sequence[str]:
    """Yields account (<crypto>, <path>, <address>) records for the desired cryptocurrencies at paths.

    """
    yield from zip( *[
        addresses(
            master_secret	= master_secret,
            crypto		= cry,
            paths		= pth,
            format		= fmt,
            allow_unbounded	= allow_unbounded,
            passphrase		= passphrase,
            using_bip39		= using_bip39,
        )
        for cry,pth,fmt in cryptopaths_parser(
            cryptopaths,
            edit		= edit,
            hardened_defaults	= hardened_defaults,
            format		= format,
        )
    ])
