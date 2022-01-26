import codecs
import logging

import hdwallet

__all__				= ( "Account", "path_edit" )

log				= logging.getLogger( __package__ )


def path_edit(
    path: str,
    edit: str,
):
    """Replace the current path w/ the new path, either entirely, or if only partially if a continuation
    '.../' followed by some new path segments is provided.

    """
    if edit.startswith( '..' ):
        new_segs	= edit.lstrip( './' ).split( '/' )
        cur_segs	= path.split( '/' )
        log.info( f"Using {edit} to replace last {len(new_segs)} of {path} with {'/'.join(new_segs)}" )
        if len( new_segs ) >= len( cur_segs ):
            raise ValueError( f"Cannot use {edit} to replace last {len(new_segs)} of {path} with {'/'.join(new_segs)}" )
        res_segs	= cur_segs[:len(cur_segs)-len(new_segs)] + new_segs
        return '/'.join( res_segs )
    else:
        return edit


class Account( hdwallet.HDWallet ):

    """Supports producing Legacy addresses for Bitcoin, and Litecoin.  Doge (D...) and Ethereum (0x...)
    addresses use standard BIP44 derivation.


    | Crypto | Semantic | Path             | Address |
    |        |          |                  | <       |
    |--------+----------+------------------+---------|
    | ETH    | Legacy   | m/44'/60'/0'/0/0 | 0x...   |
    | BTC    | Legacy   | m/44'/ 0'/0'/0/0 | 1...    |
    |        | SegWit   | m/44'/ 0'/0'/0/0 | 3...    |
    |        | Bech32   | m/84'/ 0'/0'/0/0 | bc1...  |
    | LTC    | Legacy   | m/44'/ 2'/0'/0/0 | L...    |
    |        | SegWit   | m/44'/ 2'/0'/0/0 | M...    |
    |        | Bech32   | m/84'/ 2'/0'/0/0 | ltc1... |
    | DOGE   | Legacy   | m/44'/ 3'/0'/0/0 | D...    |

    """
    CRYPTOCURRENCIES		= ('ETH', 'BTC', 'LTC', 'DOGE',)  # Currently supported
    CRYPTO_NAMES		= dict(
        ethereum	= 'ETH',
        bitcoin		= 'BTC',
        litecoin	= 'LTC',
        dogecoin	= 'DOGE',
    )

    CRYPTO_FORMAT		= dict(
        ETH		= "legacy",
        BTC		= "bech32",
        LTC		= "bech32",
        DOGE		= "legacy",
    )
    FORMATS		= ("legacy", "segwit", "bech32")

    CRYPTO_FORMAT_PATH		= dict(
        ETH		= dict(
            legacy	= "m/44'/60'/0'/0/0",
        ),
        BTC		= dict(
            legacy	= "m/44'/0'/0'/0/0",
            segwit	= "m/44'/0'/0'/0/0",
            bech32	= "m/84'/0'/0'/0/0",
        ),
        LTC		= dict(
            legacy	= "m/44'/2'/0'/0/0",
            segwit	= "m/44'/2'/0'/0/0",
            bech32	= "m/84'/2'/0'/0/0",
        ),
        DOGE		= dict(
            legacy	="m/44'/3'/0'/0/0",
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
            raise ValueError( f"{format} not supported for {crypto}; specify one of {', '.join( cls.CRYPTO_FORMAT_PATH[crypto].keys() )}" )
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
            raise ValueError( f"{crypto} address format {format!r} not recognized; specify one of {', '.join( cls.FORMATS )}" )
        cls.CRYPTO_FORMAT[crypto]	= format

    @classmethod
    def supported( cls, crypto ):
        """Validates that the specified cryptocurrency is supported and returns the normalized short name
        for it, or raises an a ValueError.  Eg. "Ethereum" --> "ETH"

        """
        validated			= cls.CRYPTO_NAMES.get(
            crypto.lower(),
            crypto.upper() if crypto.upper() in cls.CRYPTOCURRENCIES else None
        )
        if validated:
            return validated
        raise ValueError( f"{crypto} not presently supported; specify {', '.join( cls.CRYPTOCURRENCIES )}" )

    def __init__( self, crypto, format=None ):
        crypto			= Account.supported( crypto )
        self.format		= format.lower() if format else Account.address_format( crypto )
        if self.format in ("legacy", "segwit",):
            self.hdwallet	= hdwallet.BIP44HDWallet( symbol=crypto )
        elif self.format in ("bech32",):
            self.hdwallet	= hdwallet.BIP84HDWallet( symbol=crypto )
        else:
            raise ValueError( f"{crypto} does not support address format {self.format}" )

    def from_seed( self, seed: str, path: str = None ) -> "Account":
        """Derive the Account from the supplied seed and (optionally) path; uses the default derivation path
        for the Account address format, if None provided.

        """
        if type( seed ) is bytes:
            seed		= codecs.encode( seed, 'hex_codec' ).decode( 'ascii' )
        self.hdwallet.from_seed( seed )
        self.from_path( path )
        return self

    def from_path( self, path: str = None ) -> "Account":
        """Change the Account to derive from the provided path.

        If a partial path is provided (eg "...1'/0/3"), then use it to replace the given segments in
        current account path, leaving the remainder alone.

        """
        if path:
            path		= path_edit( self.path, path )
        else:
            path		= Account.path_default( self.crypto, self.format )
        self.hdwallet.clean_derivation()
        self.hdwallet.from_path( path )
        return self

    @property
    def address( self ):
        if self.format == "legacy":
            return self.hdwallet.p2pkh_address()
        elif self.format == "segwit":
            return self.hdwallet.p2sh_address()
        elif self.format == "bech32":
            return self.hdwallet.p2wpkh_address()
        raise ValueError( f"Unknown addresses semantic: {self.format}" )

    @property
    def crypto( self ):
        return self.hdwallet._cryptocurrency.SYMBOL

    @property
    def path( self ):
        return self.hdwallet.path()

    @property
    def key( self ):
        return self.hdwallet.private_key()
