
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
from enum		import Enum

from rlp		import encode as rlp_encode

from web3		import Web3

from ..util		import into_bytes


def contract_address(
    address,			# Address that is constructing the contract
    salt	= None,
    creation	= None,
    nonce	= None,		# traditional CREATE used address/nonce
):
    """Deduces the Contract Address that will result from a CREATE2 contract given the the contract
     creator's 'address', a 'salt' and the contract 'creation' bytecode.

    """
    b_address			= into_bytes( address )
    assert isinstance( b_address, bytes ) and len( b_address ) == 20, \
        f"Expected 20-byte adddress, got {b_address!r}"

    if nonce is not None and salt is None and creation is None:
        # A CREATE (traditional, or transaction-based) contract creation
        assert isinstance( nonce, int ), \
            f"The nonce for CREATE must be an integer, not {nonce!r}"
        b_result		= Web3.keccak( rlp_encode([ b_address, nonce ]) )
    else:
        assert salt is not None and creation is not None and nonce is None, \
            f"Need salt and creation bytecode for CREATE2"
        b_pre			= into_bytes( '0xff' )
        b_salt			= into_bytes( salt )
        assert len( b_salt ) == 32, \
            f"Expected 32-byte salt, got {len(b_salt)} bytes"
        b_creation		= into_bytes( creation )
        b_result		= Web3.keccak( b_pre + b_address + b_salt + Web3.keccak( b_creation ))

    result_address		= Web3.to_checksum_address( b_result[12:].hex() )

    return result_address
