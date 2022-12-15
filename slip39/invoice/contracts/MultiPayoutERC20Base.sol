// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "../openzeppelin-contracts/contracts/security/ReentrancyGuard.sol";
import "../openzeppelin-contracts/contracts/access/Ownable.sol";
import {
    IERC20Metadata as IERC20  // w/ decimals()
} from "../openzeppelin-contracts/contracts/token/ERC20/extensions/IERC20Metadata.sol";

// 
// Implements all the ERC-20 handling for MultiPayoutERC20
// 
// Allows other contracts that know about MultiPayoutERC20 (such as MultiPayoutERC20Forwarder) to
// access data about the supported ERC-20s.
// 
abstract contract MultiPayoutERC20Base is ReentrancyGuard, Ownable {
    // 
    // __SELF -- specific at construction, and used to support ...Forwarder collection
    // 
    // NOTE: immutable variables are assigned once at construction, and the construction code is
    // modified to contain the value in-place, so "access" to these immutable values in code
    // does NOT actually interrogate the contract's data!  Thus, in "delegatecall"-ed code,
    // we can safely use these values.
    // 
    address private immutable	__SELF	= address( this );

    modifier isDelegated() {
        require( address( this ) != __SELF );
	_;
    }
    modifier notDelegated() {
        require( address( this ) == __SELF );
	_;
    }

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
		    erc20s[i]		= erc20s[erc20s.length - 1];
		}
		erc20s.pop();
		return true;
	    }
	}
	return false;
    }

    //
    // Anyone can delegatecall this function, to forward all of their ERC-20 tokens into this contract
    //
    // Used by MultiPayoutERC20Forwarder to collect its ERC-20 tokens.
    // 
    // Not recommended for general public use, but you can call it if you want! ;)
    //
    // REENTRANCY ATTACK
    // 
    // It is not necessary to protect this from reentrancy, if only reputable ERC-20 tokens
    // are included.  A disreputable ERC-20 token's transfer function could re-enter this
    // call, resulting in the same token transfers being re-attempted, and subsequent transfers
    // delayed.	 But, only its own failure to implement check-effects-interactions can be exploited.
    //
    function erc20s_collector()
	external
	isDelegated  // Only delegatecall allowed!  We'll be transferring from the caller's address( this )
    {
	for ( uint256 i = MultiPayoutERC20Base( __SELF ).erc20s_len(); i > 0; --i ) {
	    IERC20		token	= MultiPayoutERC20Base( __SELF ).erc20s( i-1 );
	    try token.balanceOf( address( this )) returns ( uint256 balance ) {
		if ( balance > 0 ) {
		    // Forward the caller's balance to the recipient (this contract!)
		    try token.transfer( __SELF, balance ) returns ( bool ) {
			// ignore failing ERC-20 transfer
		    } catch {
			// ignore exception on ERC-20 transfer
		    }
		}
	    } catch {
		// ignore exception on ERC-20 balanceOf
	    }
	}
    }
}
