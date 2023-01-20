import requests
import re
import sys
import json
import logging
import traceback

from pathlib		import Path
from web3		import Web3

from .ethereum		import Chain, tokeninfos
from ..util		import commas

log				= logging.getLogger( "Tokens" )

top_100_url			= "https://etherscan.io/tokens?ps=100&p=1"


def scrapetokens( htmlfile ):
    """Scrape the top 100 ERC-20 tokens from Etherscan (or from such a file)."""

    if htmlfile:
        with open( htmlfile, 'r' ) as f:
            response_text	= f.read()
    else:
        # Probably won't work; Cloudflare scrape shielding?
        response		= requests.get(
            top_100_url,
            params	= dict(
                ps		= 100,
                p		= 1,
            )
        )
        assert response.status_code == 200, \
            f"Failed: {response.text}"
        response_text		= response.text
    # support anything with a link to [goerli.]etherscan.io/{token,address}/0x...
    for token_m in re.finditer( r'(?:img src="([^"]+)".{0,100})?https://(?:[a-z]+.)?etherscan.io/token/(0x[0-9a-fA-F]+)', response_text ):
        yield token_m.groups()


if __name__ == "__main__":
    # Look at any .json files specified, for a list of ERC-20 token details, or __file__.json
    # Save any token images found in Tokens/{symbol}_<size>.wepb
    erc20s			= {}
    chain, argv			= sys.argv[1],sys.argv[2:]
    chain,			= ( c for c in Chain if c.name.lower() == chain.lower() )

    # See if any .json files are specified to use; otherwise, default to eg. ./Tokens-Ethereum.json
    argv_json			= list( filter( lambda n: n.endswith( '.json' ), argv ))
    if not argv_json:
        here_json		= Path( str( Path( __file__ ).with_suffix( '' )) + f"-{chain.name}.json" )
        if here_json.exists():
            argv_json		= [ here_json ]
    here_icon			= Path( __file__ ).with_suffix( '' )
    log.warning( f"Icon path {here_icon} exists: {here_icon.exists()}" )

    for erc20sfile in argv_json:
        with open( erc20sfile, 'r' ) as f:
            for t_i in json.loads( f.read() ):
                erc20s[t_i['address']] = t_i
    log.warning( f"Loaded {len(erc20s)} known ERC-20 tokens from {len(argv_json)} JSON files" )

    # Look at any remaining files specified, as HTML containing etherescan.io/token/... addresses
    argv_html			= list( filter( lambda n: n not in argv_json, argv ))
    erc20s_n			= {}
    for htmlfile in argv_html:
        htmlpath		= Path( htmlfile )
        for image,token in scrapetokens( htmlpath ):
            # See if we've already seen the token; otherwise, get its info
            try:
                t		= Web3.to_checksum_address( token )
                if t not in erc20s:
                    erc20s_n[t], = tokeninfos( t, chain=chain )
                    log.warning( f"Found {erc20s_n[t]['symbol']:8}: {t}" )
            except Exception as exc:
                log.warning( f"Failed to query {token}: {exc}; {traceback.format_exc()}" )
                continue

            # See if we've already got its image; otherwise, collect it.
            info		= erc20s.get( t, erc20s_n.get( t ))
            symbol		= info['symbol']
            if here_icon.exists() and image:
                log.warning( f"Found image: {image}" )
                found_icon	= htmlpath.resolve().parent / Path( image )
                found_suff	= re.match( r".*((?:\d+)?[.].*)$", image )
                if found_suff:
                    found_suff	= found_suff.group( 1 )
                    if not found_suff.startswith( '.' ):
                        found_suff = '_'+found_suff  # w/ a size eg. 28.webp, use _28.webp
                log.warning( f"Found suffix: {found_suff}" )
                if found_icon.exists() and found_suff:
                    saved_icon	= here_icon / f"{symbol}{found_suff}"
                    log.warning( f"Found {symbol:8} token image file: {found_icon} w/ suffix: {found_suff}; moving to {saved_icon}" )
                    found_icon.rename( saved_icon )
                    info['icon'] = str( Path( *saved_icon.parts[-2:] ))

    log.warning( f"Loaded {len(erc20s_n)} new ERC-20 tokens from {len(argv_html)} HTML files" )

    erc20s_t                    = erc20s | erc20s_n
    log.warning( f"Summed {len(erc20s_t)} ERC-20 tokens" )

    # Kick out any without Ascii symbol names
    erc20s_eject		= []
    for a,i in erc20s_t.items():
        if not all( 32 < ord( c ) < 128 for c in i['symbol'] ):
            erc20s_eject.append( a )
    if erc20s_eject:
        log.warning( f"Ejecting {len(erc20s_eject)} tokens w/ bad symbols: {commas( erc20s_t[a]['name'] for a in erc20s_eject )}" )
        for a in erc20s_eject:
            del erc20s_t[a]
        log.warning( f"Left w/{len(erc20s_t)} ERC-20 tokens" )

    try:
        erc20s_list             = sorted( list( erc20s_t.values() ), key=lambda i: i['name'] )
    except Exception as exc:
        print( json.dumps( list( erc20s_t.values()), indent=4, sort_keys=True ))
        log.error( f"Failed to sort: ERC-20s list may be incorrect: {exc}" )
    else:
        print( json.dumps( erc20s_list, indent=4, sort_keys=True ))
