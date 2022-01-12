import hdwallet

__all__				= ( "Account", )


class Account( hdwallet.HDWallet ):
    @property
    def address( self ):
        return super( Account, self ).p2pkh_address()

    @property
    def crypto( self ):
        return self._cryptocurrency.SYMBOL

    @property
    def path( self ):
        return super( Account, self ).path()

    @property
    def key( self ):
        return super( Account, self ).private_key()
