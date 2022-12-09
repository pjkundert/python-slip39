// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "../openzeppelin-contracts/contracts/security/ReentrancyGuard.sol";
import "../openzeppelin-contracts/contracts/access/Ownable.sol";
import "../openzeppelin-contracts/contracts/interfaces/IERC20.sol";

// 
// Implements all the ERC-20 handling for MultiPayoutERC20
// 
// Allows other contracts that know about MultiPayoutERC20 (such as MultiPayoutERC20Forwarder) to
// access data about the supported ERC-20s.
// 
abstract contract MultiPayoutERC20Base is ReentrancyGuard, Ownable {
    // 
    // erc20s (and ..._len(), _add( IERC20 ), _del( IERC20 )
    // 
    IERC20[] public		erc20s;

    function erc20s_len()
        public
        view
	returns ( uint256 )
    { 
        return erc20s.length;
    }

    function erc20s_add(
        IERC20			_token
    ) 
        public
        onlyOwner
    {
        for ( uint256 i = 0; i < erc20s.length; ++i ) {
	    if ( erc20s[i] == _token ) {
	       return;
	    }
	}
	erc20s.push( _token );
    }

    function erc20s_del(
        IERC20			_token
    ) 
        public
        onlyOwner
        returns ( bool )
    {
        for ( uint256 i = 0; i < erc20s.length; i++ ) {
	    if ( erc20s[i]  == _token ) {
                unchecked {
                    erc20s[i]	= erc20s[erc20s.length - 1];
                }
                erc20s.pop();
                return true;
	    }
        }
        return false;
    }
}
