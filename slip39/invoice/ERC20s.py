import requests
import re
import sys
import json
import logging
import traceback

from pathlib		import Path
from web3		import Web3

from .ethereum		import tokeninfos

log				= logging.getLogger( "ERC20s" )

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

    for token_m in re.finditer( r'href="https://etherscan.io/token/(0x[0-9a-fA-F]+)"', response_text ):
        yield token_m.group( 1 )


if __name__ == "__main__":
    # Look at any .json files specified, for a list of ERC-20 token details, or __file__.json

    erc20s			= {}
    argv			= sys.argv[1:]
    argv_json			= list( filter( lambda n: n.endswith( '.json' ), argv ))
    if not argv_json:
        here_json		= Path( __file__ ).with_suffix( '.json' )
        if here_json.exists():
            argv_json		= [ here_json ]
    for erc20sfile in argv_json:
        with open( erc20sfile, 'r' ) as f:
            for t_i in json.loads( f.read() ):
                erc20s[t_i['address']] = t_i
    log.warning( f"Loaded {len(erc20s)} known ERC-20 tokens from {len(argv_json)} JSON files" )

    # Look at any remaining files specified, as HTML containing etherescan.io/token/... addresses
    argv_html			= list( filter( lambda n: n not in argv_json, argv ))
    erc20s_n			= {}
    for htmlfile in argv_html:
        for token in scrapetokens( htmlfile ):
            try:
                t		= Web3.to_checksum_address( token )
                if t not in erc20s:
                    erc20s_n[t], = tokeninfos( t )
                    log.warning( f"Found {erc20s_n[t]['symbol']!r:8}: {t}" )
            except Exception as exc:
                log.warning( f"Failed to query {token}: {exc}; {traceback.format_exc()}" )
    log.warning( f"Loaded {len(erc20s_n)} new ERC-20 tokens from {len(argv_html)} HTML files" )

    erc20s_t                    = erc20s | erc20s_n
    log.warning( f"Summed {len(erc20s_t)} ERC-20 tokens" )

    erc20s_list                 = sorted( list( erc20s_t.values() ), key=lambda i: i['name'] )

    print( json.dumps( erc20s_list, indent=4 ))
