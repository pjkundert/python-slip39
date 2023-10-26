import pytest
import http.client
import json
import os


# We don't want to run this test unless we provide our bitquery API
# key in X-API-KEY
@pytest.mark.skipif( not os.getenv( "BITQUERY_API_KEY" ), reason="Missing BITQUERY_API_KEY environment variable" )
def test_bitquery_smoke():

    queries			= [
        {
            "query": """\
query ($network: EthereumNetwork!, $addresses: [String!]) {
  ethereum(network: $network) {
    address(address: {in: $addresses}) {
      address
      annotation
      balances {
        value
        currency {
          address
          symbol
          tokenType
        }
      }
    }
  }
}
""",
            "variables": {
                "network": "ethereum",
                "addresses": [
                    "0x22615C3A31d8f9d47bdB84502780A8D2C136fCF5"
                ]
            }
        },
        {
            "query": """\
query ($network: BitcoinNetwork!, $addresses: [String!]) {
  bitcoin(network: $network) {
    inbound: coinpath(receiver: {in: $addresses}) {
      receiver {
        address
      }
      amount
    }
  }
}
""",
            "variables": {
                "network": "bitcoin",
                "addresses": [
                    "bc1qcj9ujyvrf94wu0902g2lnklzlyn5j5nrr44hwp",
                    "18cBEMRxXHqzWWCxZNtU91F5sbUNKhL5PX",
                    "bc1qygm3dlynmjxuflghr0hmq6r7wmff2jd5gtgz0q"
                ]
            }
        }
    ]

    headers = {
        'Content-Type': 'application/json',
        'X-API-KEY': os.getenv( "BITQUERY_API_KEY" ),
    }

    conn = http.client.HTTPSConnection("graphql.bitquery.io")

    for query in queries:
        payload = json.dumps( query )
        print( payload )

        conn.request("POST", "/", payload, headers)
        rx = conn.getresponse()
        rxstr = rx.read().decode("UTF-8")
        print(rxstr)
        response = json.loads( rxstr )
        print( json.dumps( response, indent=4 ))
