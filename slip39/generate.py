import codecs
import logging
import secrets
from collections	import namedtuple
from typing		import Dict, List, Sequence, Tuple

import eth_account

from shamir_mnemonic	import generate_mnemonics

from .defaults		import PATH_ETH_DEFAULT, BITS_DEFAULT, MNEM_ROWS_COLS
from .util		import ordinal

RANDOM_BYTES			= secrets.token_bytes

log				= logging.getLogger( __package__ )


def random_secret(
    seed_length			= BITS_DEFAULT // 8
) -> bytes:
    return RANDOM_BYTES( seed_length )


Details = namedtuple( 'Details', ('name', 'group_threshold', 'groups', 'accounts') )


def enumerate_mnemonic( mnemonic ):
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


def create(
    name: str,
    group_threshold: int,
    groups: Dict[str,Tuple[int, int]],
    master_secret: bytes	= None,		# Default: 128-bit seeds
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
    if log.isEnabledFor( logging.INFO ):
        group_reqs			= list(
            f"{g_nam}({g_of}/{len(g_mns)})" if g_of != len(g_mns) else f"{g_nam}({g_of})"
            for g_nam,(g_of,g_mns) in groups.items() )
        requires		= f"Recover w/ {group_threshold} of {len(groups)} groups {', '.join(group_reqs)}"
        for g_n,(g_name,(g_of,g_mnems)) in enumerate( groups.items() ):
            log.info( f"{g_name}({g_of}/{len(g_mnems)}): {requires}" )
            for mn_n,mnem in enumerate( g_mnems ):
                for line,_ in organize_mnemonic( mnem, label=f"{ordinal(mn_n+1)} " ):
                    log.info( f"{line}" )
    
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
    if len( master_secret ) not in (16, 32, 64):
        raise ValueError(
            f"Only 128-, 256- and 512bit seeds supported; {len(master_secret)*8}-bit master_secret supplied" )
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
