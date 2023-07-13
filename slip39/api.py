
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

import base58
import codecs
import hashlib
import itertools
import json
import logging
import math
import re
import secrets
import string
import warnings

from functools		import wraps
from collections	import namedtuple
from typing		import Dict, List, Sequence, Tuple, Optional, Union, Callable

from shamir_mnemonic	import generate_mnemonics

import hdwallet
from hdwallet		import cryptocurrencies

from .defaults		import BITS_DEFAULT, BITS, MNEM_ROWS_COLS, GROUP_REQUIRED_RATIO, CRYPTO_PATHS
from .util		import ordinal, commas
from .recovery		import produce_bip39, recover_bip39

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
    warnings.warn( message, ImportWarning )
    log.warning( message )
    if log.isEnabledFor( logging.DEBUG ):
        log.exception( message )
    paper_wallet_issues.append( message )

try:
    import eth_account
except ImportError as exc:
    eth_account			= None
    message			= f"Unable to support Paper Wallet output: {exc}"
    warnings.warn( message, ImportWarning )
    log.warning( message )
    if log.isEnabledFor( logging.DEBUG ):
        log.exception( message )
    paper_wallet_issues.append( message )


RANDOM_BYTES			= secrets.token_bytes


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
    """Replace the current path w/ the new path, either entirely, or if only partially if a continuation
    '../' followed by some new path segments is provided.

    """
    if edit.startswith( '.' ):
        new_segs	= edit.lstrip( './' ).split( '/' )
        cur_segs	= path.split( '/' )
        log.debug( f"Using {edit} to replace last {len(new_segs)} of {path} with {'/'.join(new_segs)}" )
        if len( new_segs ) >= len( cur_segs ):
            raise ValueError( f"Cannot use {edit} to replace last {len(new_segs)} of {path} with {'/'.join(new_segs)}" )
        res_segs	= cur_segs[:len(cur_segs)-len(new_segs)] + new_segs
        return '/'.join( res_segs )
    else:
        return edit


class CronosMainnet( cryptocurrencies.Cryptocurrency ):

    NAME = "Cronos"
    SYMBOL = "CRO"
    NETWORK = "mainnet"
    SOURCE_CODE = "https://github.com/crypto-org-chain/chain-main"
    COIN_TYPE = cryptocurrencies.CoinType({
        "INDEX": 60,
        "HARDENED": True
    })

    SCRIPT_ADDRESS = 0x05
    PUBLIC_KEY_ADDRESS = 0x00
    SEGWIT_ADDRESS = cryptocurrencies.SegwitAddress({
        "HRP": "crc",
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


class BinanceMainnet( cryptocurrencies.Cryptocurrency ):

    NAME = "Binance"
    SYMBOL = "BNB"
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


class RippleMainnet( cryptocurrencies.Cryptocurrency ):
    """The standard HDWallet.p2pkh_address (Pay to Public Key Hash) encoding is used, w/ a prefix of
    00.  However, the XRP-specific base-58 encoding is used, resulting in a fixed 'r' prefix.

    See: https://xrpl.org/accounts.html#address-encoding.

    """
    NAME = "Ripple"
    SYMBOL = "XRP"
    NETWORK = "mainnet"
    SOURCE_CODE = "https://github.com/ripple/rippled"
    COIN_TYPE = cryptocurrencies.CoinType({
        "INDEX": 144,
        "HARDENED": True
    })

    PUBLIC_KEY_ADDRESS = 0x00  # Results in the prefix r..., when used w/ the Ripple base-58 alphabet
    SEGWIT_ADDRESS = cryptocurrencies.SegwitAddress({
        "HRP": None,
        "VERSION": 0x00
    })

    EXTENDED_PRIVATE_KEY = cryptocurrencies.ExtendedPrivateKey({
        "P2PKH": None,
        "P2SH": None,
        "P2WPKH": None,
        "P2WPKH_IN_P2SH": None,
        "P2WSH": None,
        "P2WSH_IN_P2SH": None,
    })
    EXTENDED_PUBLIC_KEY = cryptocurrencies.ExtendedPublicKey({
        "P2PKH": None,
        "P2SH": None,
        "P2WPKH": None,
        "P2WPKH_IN_P2SH": None,
        "P2WSH": None,
        "P2WSH_IN_P2SH": None,
    })

    MESSAGE_PREFIX = None
    DEFAULT_PATH = f"m/44'/{str(COIN_TYPE)}/0'/0/0"
    WIF_SECRET_KEY = 0x80


class XRPHDWallet( hdwallet.HDWallet ):
    """The XRP address format uses the standard p2pkh_address formulation, from
    https://xrpl.org/accounts.html#creating-accounts:

    The ripemd160 hash of sha256 hash of public key, then base58-encoded w/ 4-byte checksum.  The
    base-58 dictionary used is the standard Ripple (not Bitcoin!) alphabet:

        rpshnaf39wBUDNEGHJKLM4PQRST7VWXYZ2bcdeCg65jkm8oFqi1tuvAxyz

    NOTE: Only secp256k1 keypairs are supported; these are the default for the Ripple ledger.

    """
    def p2pkh_address( self ):
        p2pkh_btc	= super( XRPHDWallet, self ).p2pkh_address()
        p2pkh		= base58.b58decode_check( p2pkh_btc )
        return base58.b58encode_check( p2pkh, base58.RIPPLE_ALPHABET ).decode( 'UTF-8' )


class Account:
    """A Cryptocurrency "Account" / Wallet, based on a variety of underlying Python crypto-asset
    support modules.  Presently, only meherett/python-hdwallet is used.

    An appropriate hdwallet-like wrapper is built, for any crypto-asset supported using another
    module.  The required hdwallet API calls are:

      .from_seed	-- start deriving from the provided seed
      .from_mnemonic	-- start deriving from the provided seed via BIP-39 mnemonic
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
    | BNB    | Legacy   | m/44'/ 60'/0'/0/0 | 0x...   | Beta    |
    | CRO    | Bech32   | m/44'/ 60'/0'/0/0 | crc1... | Beta    |
    | BTC    | Legacy   | m/44'/  0'/0'/0/0 | 1...    |         |
    |        | SegWit   | m/49'/  0'/0'/0/0 | 3...    |         |
    |        | Bech32   | m/84'/  0'/0'/0/0 | bc1...  |         |
    | LTC    | Legacy   | m/44'/  2'/0'/0/0 | L...    |         |
    |        | SegWit   | m/49'/  2'/0'/0/0 | M...    |         |
    |        | Bech32   | m/84'/  2'/0'/0/0 | ltc1... |         |
    | DOGE   | Legacy   | m/44'/  3'/0'/0/0 | D...    |         |
    | XRP    | Legacy   | m/44'/144'/0'/0/0 | r...    | Beta    |

    """
    CRYPTO_NAMES		= dict(  # Currently supported (in order of visibility)
        ethereum	= 'ETH',
        bitcoin		= 'BTC',
        litecoin	= 'LTC',
        dogecoin	= 'DOGE',
        cronos		= 'CRO',
        binance		= 'BNB',
        ripple		= 'XRP',
    )
    CRYPTOCURRENCIES		= set( CRYPTO_NAMES.values() )
    CRYPTOCURRENCIES_BETA	= set( ('BNB', 'CRO', 'XRP') )

    ETHJS_ENCRYPT		= set( ('ETH', 'CRO', 'BNB') )		# Can be encrypted w/ Ethereum JSON wallet
    BIP38_ENCRYPT		= CRYPTOCURRENCIES - ETHJS_ENCRYPT      # Can be encrypted w/ BIP-38

    CRYPTO_FORMAT		= dict(
        ETH		= "legacy",
        BTC		= "bech32",
        LTC		= "bech32",
        DOGE		= "legacy",
        CRO		= "bech32",
        BNB		= "legacy",
        XRP		= "legacy",
    )

    # Any locally-defined python-hdwallet classes, cryptocurrency definitions, and any that may
    # require some adjustments when calling python-hdwallet address and other functions.
    CRYPTO_WALLET_CLS		= dict(
        XRP		= XRPHDWallet,
    )
    CRYPTO_LOCAL		= dict(
        CRO		= CronosMainnet,
        BNB		= BinanceMainnet,
        XRP		= RippleMainnet,
    )
    CRYPTO_LOCAL_SYMBOL		= dict(
        BNB		= "ETH"
    )

    # The available address formats and default derivation paths.
    FORMATS		= ("legacy", "segwit", "bech32")

    CRYPTO_FORMAT_PATH		= dict(
        ETH		= dict(
            legacy	= "m/44'/60'/0'/0/0",
        ),
        BNB		= dict(
            legacy	= "m/44'/60'/0'/0/0",
        ),
        CRO		= dict(
            bech32	= "m/44'/60'/0'/0/0",
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
        """Validates that the specified cryptocurrency is supported and returns the normalized short name
        for it, or raises an a ValueError.  Eg. "Ethereum" --> "ETH"

        """
        validated		= cls.CRYPTO_NAMES.get(
            crypto.lower(),
            crypto.upper() if crypto.upper() in cls.CRYPTOCURRENCIES else None
        )
        if validated:
            return validated
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
        hdwallet_cls		= self.CRYPTO_WALLET_CLS.get( crypto )
        if hdwallet_cls is None and self.format in ("legacy", "segwit",):
            hdwallet_cls	= hdwallet.BIP44HDWallet
        if hdwallet_cls is None and self.format in ("bech32",):
            hdwallet_cls	= hdwallet.BIP84HDWallet
        if hdwallet_cls is None:
            raise ValueError( f"{crypto} does not support address format {self.format}" )
        self.hdwallet		= hdwallet_cls( symbol=crypto, cryptocurrency=cryptocurrency )

    def from_seed( self, seed: str, path: str = None ) -> "Account":
        """Derive the Account from the supplied seed and (optionally) path; uses the default derivation path
        for the Account address format, if None provided.

        """
        if type( seed ) is bytes:
            seed		= codecs.encode( seed, 'hex_codec' ).decode( 'ascii' )
        self.hdwallet.from_seed( seed )
        self.from_path( path )
        return self

    def from_mnemonic( self, mnemonic: str, path: str = None ) -> "Account":
        """Derive the Account from the supplied BIP-39 mnemonic and (optionally) path; uses the
        default derivation path for the Account address format, if None provided.

        """
        self.hdwallet.from_mnemonic( mnemonic )
        self.from_path( path )
        return self

    def from_xpubkey( self, xpubkey: str, path: str = None ) -> "Account":
        """Derive the Account from the supplied xpubkey and (optionally) path; uses default
        derivation path for the Account address format, if None provided.

        Since this xpubkey may have been generated at an arbitrary path, eg.

            m/44'/60'/0'

        any subsequent path provided, such as "m/0/0" will give us the address at
        effective path:

            m/44'/60'/0'/0/0

        However, if we ask for the path from this account, it will return:

            m/0/0

        It is impossible to correctly recover any "hardened" accounts from an xpubkey, such as
        "m/1'/0".  These would need access to the private key material, which is missing.
        Therefore, the original account (or an xprivkey) would be required to access the desired
        path:

            m/44'/60'/0'/1'/0

        """
        self.hdwallet.from_xpublic_key( xpubkey )
        self.from_path( path )
        return self

    def from_xprvkey( self, xprvkey: str, path: str = None ) -> "Account":
        self.hdwallet.from_xprivate_key( xprvkey )
        self.from_path( path )
        return self

    def from_path( self, path: str = None ) -> "Account":
        """Change the Account to derive from the provided path.

        If a partial path is provided (eg "...1'/0/3"), then use it to replace the given segments in
        current (or the default) account path, leaving the remainder alone.

        If the derivation path is empty (only "m/") then leave the Account at clean_derivation state

        """
        from_path		= self.path or Account.path_default( self.crypto, self.format )
        if path:
            from_path		= path_edit( from_path, path )
        self.hdwallet.clean_derivation()
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
        return self.hdwallet.p2pkh_address()

    def segwit_address( self ):
        return self.hdwallet.p2sh_address()

    def bech32_address( self ):
        return self.hdwallet.p2wpkh_address()

    @property
    def crypto( self ):
        return self.hdwallet._cryptocurrency.SYMBOL

    @property
    def path( self ):
        return self.hdwallet.path()

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
        """Returns the xpub, ypub or zpub, depending on whether format is legacy, segwit or bech32"""
        return self.hdwallet.xpublic_key()

    def from_private_key( self, private_key ):
        self.hdwallet.from_private_key( private_key )
        return self

    def encrypted( self, passphrase ):
        """Output the appropriately encrypted private key for this cryptocurrency.  Ethereum uses
        encrypted JSON wallet standard, Bitcoin et.al. use BIP-38 encrypted private keys."""
        if self.crypto in self.ETHJS_ENCRYPT:
            if not eth_account:
                raise NotImplementedError( "The eth-account module is required to support Ethereum JSON wallet encryption; pip install slip39[wallet]" )
            wallet_dict		= eth_account.Account.encrypt( self.key, passphrase )
            return json.dumps( wallet_dict, separators=(',',':') )
        return self.bip38( passphrase )

    def from_encrypted( self, encrypted_privkey, passphrase, strict=True ):
        """Import the appropriately decrypted private key for this cryptocurrency."""
        if self.crypto in self.ETHJS_ENCRYPT:
            if not eth_account:
                raise NotImplementedError( "The eth-account module is required to support Ethereum JSON wallet decryption; pip install slip39[wallet]" )
            private_hex		= bytes( eth_account.Account.decrypt( encrypted_privkey, passphrase )).hex()
            self.from_private_key( private_hex )
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
        key			= scrypt( passphrase, salt=ahash, key_len=64, N=16384, r=8, p=8 )
        derivedhalf1		= key[0:32]
        derivedhalf2		= key[32:64]
        aes			= AES.new( derivedhalf2, AES.MODE_ECB )
        enchalf1		= aes.encrypt( ( int( private_hex[ 0:32], 16 ) ^ int.from_bytes( derivedhalf1[ 0:16], 'big' )).to_bytes( 16, 'big' ))
        enchalf2		= aes.encrypt( ( int( private_hex[32:64], 16 ) ^ int.from_bytes( derivedhalf1[16:32], 'big' )).to_bytes( 16, 'big' ))
        prefix			= b'\x01\x42'
        encrypted_privkey	= prefix + flagbyte + ahash + enchalf1 + enchalf2
        # Encode the encrypted private key to base58, adding the 4-byte base58 check suffix
        return base58.b58encode_check( encrypted_privkey ).decode( 'UTF-8' )

    def from_bip38( self, encrypted_privkey, passphrase, strict=True ):
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
        key			= scrypt( passphrase, salt=ahash, key_len=64, N=16384, r=8, p=8 )
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
        self.from_private_key( private_hex )
        addr			= self.legacy_address().encode( 'UTF-8' )  # Eg. b"184xW5g..."
        ahash_confirm		= hashlib.sha256( hashlib.sha256( addr ).digest() ).digest()[0:4]
        if ahash_confirm != ahash:
            warning		= f"BIP-38 address hash verification failed ({ahash_confirm.hex()} != {ahash.hex()}); password may be incorrect."
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


def cryptopaths_parser( cryptocurrency, edit=None, hardened_defaults=False ):
    """Generate a standard cryptopaths list, from the given sequnce of (<crypto>,<paths>) or
    "<crypto>[:<paths>]" cryptocurrencies (default: CRYPTO_PATHS, optionally w/ only the hardened
    portion of the path, eg. omitting the trailing ../0/0).

    Adjusts the provided derivation paths by an optional eg. "../-" path adjustment.

    """
    cryptopaths 		= []
    for crypto in cryptocurrency or CRYPTO_PATHS:
        try:
            if type(crypto) is str:
                crypto,paths	= crypto.split( ':' )   # A sequence of str
            else:
                crypto,paths	= crypto                # A sequence of tuples
        except ValueError:
            crypto,paths	= crypto,None
        crypto			= Account.supported( crypto )
        if paths is None:
            paths		= Account.path_default( crypto )
            if hardened_defaults:
                paths,_		= path_hardened( paths )
        if edit:
            paths		= path_edit( paths, edit )
        cryptopaths.append( (crypto,paths) )
    return cryptopaths


def random_secret(
    seed_length			= BITS_DEFAULT // 8
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
    return RANDOM_BYTES( seed_length )


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
        (:? (?P<require> \d* ) \s* / )?
        \s*
        (?P<size> \d* )
        \s*\)?\s*
        $""", re.VERBOSE )


def create(
    name: str,
    group_threshold: int,
    groups: Dict[str,Tuple[int, int]],
    master_secret: bytes	= None,	        # Default: generate 128-bit Seed Entropy
    passphrase: bytes		= b"",
    using_bip39: bool		= False,        # Produce wallet Seed from master_secret Entropy using BIP-39 generation
    iteration_exponent: int	= 1,
    cryptopaths: Optional[Sequence[Union[str,Tuple[str,str]]]] = None,  # default: ETH, BTC at default paths
    strength: int		= 128,
) -> Tuple[str,int,Dict[str,Tuple[int,List[str]]], Sequence[Sequence[Account]], bool]:
    """Creates a SLIP-39 encoding for supplied master_secret Entropy, and 1 or more Cryptocurrency
    accounts.  Returns the Details, in a form directly compatible with the layout.produce_pdf API.

    The master_secret Seed Entropy is discarded (because it is, of course, always recoverable from
    the SLIP-39 mnemonics).

    Creates accountgroups derived from the Seed Entropy.  By default, this is done in the SLIP-39
    standard, using the master_secret Entropy directly.  If a passphrase is supplied, this is also
    used in the SLIP-39 standard fashion (not recommended -- not Trezor "Model T" compatible).

    If using_bip39, creates the Cryptocurrency accountgroups from the supplied master_secret
    Entropy, by generating the Seed from a BIP-38 Mnemonic produced from the provided entropy
    (or generated, default 128 bits), plus any supplied passphrase.

    """
    if master_secret is None:
        assert strength in BITS, f"Invalid {strength}-bit secret length specified"
        master_secret		= random_secret( strength // 8 )

    g_names,g_dims		= list( zip( *groups.items() ))

    # Derive the desired account(s) at the specified derivation paths, or the default, using either
    # BIP-39 Seed generation, or directly from Entropy for SLIP-39.
    if using_bip39:
        # For BIP-39, the passphrase is consumed here, and Cryptocurrency accounts are generated
        # using the BIP-39 Seed generated from entropy + passphrase
        bip39_mnem		= produce_bip39( entropy=master_secret )
        bip39_seed		= recover_bip39(
            mnemonic	= bip39_mnem,
            passphrase	= passphrase,
        )
        log.info(
            f"SLIP-39 for {name} from {len(master_secret)*8}-bit Entropy using BIP-39 Mnemonic" + (
                f": {bip39_mnem:.10}... (w/ BIP-39 Passphrase: {passphrase!r:.2}..."  # WARNING: Reveals partial Secret!
                if log.isEnabledFor( logging.DEBUG ) else ""
            )
        )
        accts			= list( accountgroups(
            master_secret	= bip39_seed,
            cryptopaths		= cryptopaths,
            allow_unbounded	= False,
        ))
        passphrase		= b""
    else:
        # For SLIP-39, accounts are generated directly from supplied Entropy, and passphrase
        # encrypts the SLIP-39 Mnemonics, below.
        log.info(
            f"SLIP-39 for {name} from {len(master_secret)*8}-bit Entropy directly" + (
                f": {codecs.encode( master_secret, 'hex_codec' ).decode( 'ascii' ):.10}... (w/ SLIP-39 Passphrase: {passphrase!r:.2}..."  # WARNING: Reveals partial Secret!
                if log.isEnabledFor( logging.DEBUG ) else ""
            )
        )
        accts			= list( accountgroups(
            master_secret	= master_secret,
            cryptopaths		= cryptopaths,
            allow_unbounded	= False,
        ))

    # Generate the SLIP-39 Mnemonics representing the supplied master_secret Seed Entropy.  This
    # always recovers the Seed Entropy; if not using_bip39, this is also the wallet derivation Seed;
    # if using_bip39, the wallet derivation Seed was produced from the BIP-39 Seed generation
    # process (and the SLIP-39 password is always b"", here).
    mnems			= mnemonics(
        group_threshold	= group_threshold,
        groups		= g_dims,
        master_secret	= master_secret,
        passphrase	= passphrase,
        iteration_exponent= iteration_exponent
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
            log.info( f"{g_name}({g_of}/{len(g_mnems)}): {requires}" )
            for mn_n,mnem in enumerate( g_mnems ):
                for line,_ in organize_mnemonic( mnem, label=f"{ordinal(mn_n+1)} " ):
                    log.info( f"{line}" )

    return Details(name, group_threshold, groups, accts, using_bip39)


def mnemonics(
    group_threshold: int,
    groups: Sequence[Tuple[int, int]],
    master_secret: Union[str,bytes] = None,
    passphrase: bytes		= b"",
    iteration_exponent: int	= 1,
    strength: int		= 128,
) -> List[List[str]]:
    """Generate SLIP39 mnemonics for the supplied group_threshold of the given groups.  Will generate a
     random master_secret, if necessary.

    """
    if master_secret is None:
        assert strength in BITS, f"Invalid {strength}-bit secret length specified"
        master_secret		= random_secret( strength // 8 )
    if len( master_secret ) * 8 not in BITS:
        raise ValueError(
            f"Only {commas( BITS, final_and=True )}-bit seeds supported; {len(master_secret)*8}-bit seed supplied" )
    return generate_mnemonics(
        group_threshold	= group_threshold,
        groups		= groups,
        master_secret	= master_secret,
        passphrase	= passphrase,
        iteration_exponent = iteration_exponent )


def account(
    master_secret: Union[str,bytes],
    crypto: str			= None,  # default 'ETH'
    path: str			= None,  # default to the crypto's path_default
    format: str			= None,  # eg. 'bech32', or use the default address format for the crypto
):
    """Generate an HD wallet Account from the supplied master_secret seed, at the given HD derivation
    path, for the specified cryptocurrency.

    If the master_secret is bytes, it is used as-is.  If a str, then we generally expect it to be
    hex.  However, this is where we can detect alternatives like "{x,y,z}{pub,priv}key...".  These
    are identifiable by their prefix, which is incompatible with hex, so there is no ambiguity.

    """
    if isinstance( master_secret, bytes ) or all( c in string.hexdigits for c in master_secret ):
        acct			= Account(
            crypto	= crypto or 'ETH',
            format	= format,
        )
        acct.from_seed(
            seed	= master_secret,
            path	= path,
        )
        log.debug( f"Created {acct} from {len(master_secret)*8}-bit seed, at derivation path {path}" )
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

    return acct


def accounts(
    master_secret: Union[str,bytes],
    crypto: str			= None,  # default 'ETH'
    paths: str			= None,  # default to the crypto's path_default; allow ranges
    format: str			= None,
    allow_unbounded		= True,
):
    """Create accounts for crypto, at the provided paths (allowing ranges), with the optionsal address format. """
    for path in [None] if paths is None else path_sequence( *path_parser(
        paths		= paths,
        allow_unbounded	= allow_unbounded,
    )):
        yield account( master_secret, crypto=crypto, path=path, format=format )


def accountgroups(
    master_secret: Union[str,bytes],
    cryptopaths: Optional[Sequence[Union[str,Tuple[str,str]]]] = None,  # Default: ETH, BTC
    allow_unbounded: bool	= True,
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
            crypto		= crypto,
            paths		= paths,
            allow_unbounded	= allow_unbounded,
        )
        for crypto,paths in cryptopaths_parser( cryptopaths )
    ])


def address(
    master_secret: Union[str,bytes],
    crypto: str			= None,
    path: str			= None,
    format: str			= None,
):
    """Return the specified cryptocurrency HD account address at path."""
    return account(
        master_secret,
        path		= path,
        crypto		= crypto,
        format		= format,
    ).address


def addresses(
    master_secret: Union[str,bytes],
    crypto: str	 		= None,  # default 'ETH'
    paths: str			= None,  # default: The crypto's path_default; supports ranges
    format: str			= None,
    allow_unbounded: bool	= True,
):
    """Generate a sequence of cryptocurrency account (path, address, ...)  for all designated
    cryptocurrencies.  Usually a single (<path>, <address>) tuple is desired (different
    cryptocurrencies typically have their own unique path derivations.

    """
    for acct in accounts( master_secret, crypto, paths, format, allow_unbounded=allow_unbounded ):
        yield (acct.crypto, acct.path, acct.address)


def addressgroups(
    master_secret: Union[str,bytes],
    cryptopaths: Optional[Sequence[Union[str,Tuple[str,str]]]] = None,  # Default ETH, BTC
    allow_unbounded: bool	= True,
) -> Sequence[str]:
    """Yields account (<crypto>, <path>, <address>) records for the desired cryptocurrencies at paths.

    """
    yield from zip( *[
        addresses(
            master_secret	= master_secret,
            paths		= paths,
            crypto		= crypto,
            allow_unbounded	= allow_unbounded,
        )
        for crypto,paths in cryptopaths_parser( cryptopaths )
    ])
