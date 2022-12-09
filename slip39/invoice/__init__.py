
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

from web3		import Web3

from ..util		import into_bytes

def precomputed_contract_address( address, salt, creation ):
    """Deduces the Contract Address that will result from a CREATE2 contract given the the contract
     creator's 'address', a 'salt' and the contract 'creation' bytecode.

    """
    pre				= '0xff'
    b_pre			= into_bytes( pre )
    b_address			= into_bytes( address )
    b_salt			= into_bytes( salt )
    b_creation			= into_bytes( creation )

    keccak_b_creation		= Web3.keccak( b_creation )
    b_result			= Web3.keccak( b_pre + b_address + b_salt + keccak_b_creation )
    result_address		= Web3.to_checksum_address( b_result[12:].hex() )

    return result_address
