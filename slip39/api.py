import itertools
import logging
import math
import re
import secrets

from collections	import namedtuple
from typing		import Dict, List, Sequence, Tuple, Union, Callable

from shamir_mnemonic	import generate_mnemonics

from .types		import Account
from .defaults		import BITS_DEFAULT, BITS, MNEM_ROWS_COLS, GROUP_REQUIRED_RATIO
from .util		import ordinal


RANDOM_BYTES			= secrets.token_bytes

log				= logging.getLogger( __package__ )


def path_parser(
    paths: str,
    allow_unbounded: bool	= True,
) -> Tuple[str, Dict[str, Callable[[], int]]]:
    """Create a format and a dictionary of iterators to feed into it.

    Supports paths with an arbitrary prefix, eg. 'm/' or '.../'
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
    master_secret: bytes	= None,		# Default: 128-bit seeds
    passphrase: bytes		= b"",
    iteration_exponent: int	= 1,
    cryptopaths: Sequence[Tuple[str,str]] = None,  # default: ETH, BTC at default paths
    strength: int		= 128,
) -> Tuple[str,int,Dict[str,Tuple[int,List[str]]], Sequence[Sequence[Account]]]:
    """Creates a SLIP-39 encoding and 1 or more Ethereum accounts.  Returns the details, in a form
    compatible with the output API.

    """
    if master_secret is None:
        assert strength in BITS, f"Invalid {strength}-bit secret length specified"
        master_secret		= random_secret( strength // 8 )
    g_names,g_dims		= list( zip( *groups.items() ))
    mnems			= mnemonics(
        group_threshold	= group_threshold,
        groups		= g_dims,
        master_secret	= master_secret,
        passphrase	= passphrase,
        iteration_exponent= iteration_exponent
    )
    # Derive the desired account(s) at the specified derivation paths, or the default
    accts			= list( accountgroups(
        master_secret	= master_secret,
        cryptopaths	= cryptopaths or [('ETH',None), ('BTC',None)],
        allow_unbounded	= False,
    ))

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

    return Details(name, group_threshold, groups, accts)


def mnemonics(
    group_threshold: int,
    groups: Sequence[Tuple[int, int]],
    master_secret: Union[str,bytes] = None,
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
    master_secret: Union[str,bytes],
    crypto: str			= None,  # default 'ETH'
    path: str			= None,  # default to the crypto's path_default
    format: str			= None,  # eg. 'bech32', or use the default address format for the crypto
):
    """Generate an HD wallet Account from the supplied master_secret seed, at the given HD derivation
    path, for the specified cryptocurrency.

    """
    acct			= Account(
        crypto		= crypto or 'ETH',
        format		= format,
    ).from_seed(
        seed		= master_secret,
        path		= path,
    )
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
    master_secret: bytes,
    cryptopaths: Sequence[Tuple[str,str]],
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
            paths		= paths,
            crypto		= crypto,
            allow_unbounded	= allow_unbounded,
        )
        for crypto,paths in cryptopaths
    ])


def address(
    master_secret: bytes,
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
    master_secret: bytes,
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
    master_secret: bytes,
    cryptopaths: Sequence[Tuple[str,str]],
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
        for crypto,paths in cryptopaths
    ])
