import codecs
import secrets
from collections	import namedtuple
from typing		import Dict, List, Sequence, Tuple

import eth_account

from shamir_mnemonic	import generate_mnemonics

from .defaults		import PATH_ETH_DEFAULT

RANDOM_BYTES			= secrets.token_bytes


def random_secret() -> bytes:
    return RANDOM_BYTES( 16 )


Details = namedtuple( 'Details', ('name', 'group_threshold', 'groups', 'accounts') )


def create(
    name: str,
    group_threshold: int,
    groups: Dict[str,Tuple[int, int]],
    master_secret: bytes	= None,
    passphrase: bytes		= b"",
    iteration_exponent: int	= 1,
    paths: Sequence[str]	= None,		# Default: PATH_ETH_DEFAULT
) -> Tuple[str,int,Dict[str,Tuple[int,List[str]]], Sequence[eth_account.Account]]:
    """Creates a SLIP-39 encoding and 1 or more Ethereum accounts.  Returns the details, in a form
    compatible with the output API.

    """
    if master_secret is None:
        master_secret		= random_secret()
    g_names,g_dims		= list( zip( *groups.items() ))
    mnems			= mnemonics(
        group_threshold	= group_threshold,
        groups		= g_dims,
        master_secret	= master_secret,
        passphrase	= passphrase,
        iteration_exponent= iteration_exponent
    )
    # Derive all the Ethereum accounts at the specified derivation paths, or the default
    accounts			= {
        path: account(
            master_secret= master_secret,
            path	= path
        )
        for path in paths or [PATH_ETH_DEFAULT]
    }
    groups			= {
        g_name: (g_of, g_mnems)
        for (g_name,(g_of, _),g_mnems) in zip( g_names, g_dims, mnems )
    }
    return Details(name, group_threshold, groups, accounts)


def mnemonics(
    group_threshold: int,
    groups: Sequence[Tuple[int, int]],
    master_secret: bytes	= None,
    passphrase: bytes		= b"",
    iteration_exponent: int	= 1,
) -> List[List[str]]:
    """Generate SLIP39 mnemonics for the supplied group_threshold of the given groups.  Will generate a
     random master_secret, if necessary.

    """
    if master_secret is None:
        master_secret		= random_secret()
    if len( master_secret ) != 16:
        raise ValueError(
            f"Only 128-bit (16 byte) seeds supported; {len(master_secret)*8}-bit master_secret supplied" )
    return generate_mnemonics(
        group_threshold	= group_threshold,
        groups		= groups,
        master_secret	= master_secret,
        passphrase	= passphrase,
        iteration_exponent = iteration_exponent )


def account(
    master_secret: bytes,
    path: str			= None
):
    """Generate an account from the supplied master_secret seed, at the given HD derivation path.

    """

    key				= eth_account.hdaccount.key_from_seed(
        master_secret, path or PATH_ETH_DEFAULT
    )
    keyhex			= '0x' + codecs.encode( key, 'hex_codec' ).decode( 'ascii' )
    return eth_account.Account.from_key( keyhex )
