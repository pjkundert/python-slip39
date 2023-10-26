// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// A minimal Forwarder that can be deployed using the EVM CREATE2 opcode at a 
// deterministic address.  Thus, we do not need to actually deploy the contract
// until funds appear at the address.
// 
// This process takes the initiating source address (the address of the Contract initiating the
// CREATE2), a salt and the contract creation code (which includes the constructor arguments).  Of
// course, this includes the destination address.  But importantly, in order to support a number of
// ERC-20 token Contract addresses, the Forward must know all the possible tokens *in advance* --
// support for additional tokens cannot be made *after* address creation!  For example, if you wish to
// allow the client to pay in ETH, or ERC-20 USDC or USDT, only these tokens can *ever* be supported by
// this address!
// 
// Some examples of this concept:
// 
// https://github.com/gabrieladeniji/forwarder_factory/blob/main/contracts/ForwarderFactory.sol
// 
// Our forwarder is a one-shot, where the constructore executes all ERC-20 transfers and finally uses
// selfdestruct to clear out the account's ETH and destroy the contract, reducing its Gas cost.
// Since this is a "push" payment, we must carefully wrap any ERC-20 calls ignoring errors, in 
// case one or more of the supported ERC-20 contracts is selfdestructed or is otherwise faulty.
// Since all operations occur during Forwarder construction, no reentrancy is possible.
//
// Coinbase uses/used(?) something like this to manage their merchant payment wallets:
// 
// https://web.archive.org/web/20190814233503/https://blog.coinbase.com/usdc-payment-processing-in-coinbase-commerce-b1af1c82fb0?gi=f79ac81c04f1
//
// Note that we can re-deploy the same contract multiple times, if desired (for example, if a client re-uses
// the same payment address multiple times):
// 
// https://forum.openzeppelin.com/t/selfdestruct-and-redeploy-in-the-same-transaction-using-create2-fails/8797
//
// This fact makes it possible to deploy 2 functionally *differing* contracts at the same address:
// 
// https://docs.soliditylang.org/en/latest/control-structures.html#salted-contract-creations-create2
// 
// Deploymenet via the CREATE2 opcode is available in Solidity >=0.8 using:
// 
//     function deploy( uint256 _salt, uint256 _arg1, address _arg2 ) returns ( address ) {
//         return address( new ContractName{ salt: _salt }( _arg1, _arg2 ));
//     }
// 
// The Contract address can be precomputed: (from https://solidity-by-example.org/app/create2/)
// 
//     function deploy_address( uint256 _salt, uint256 _arg1, address _arg2 )
//         public
//         view
//         returns ( address )
//     {
//         bytes memory contract	= type(ContractName).creationCode;
//         bytes memory creation	= abi.encodePacked( contract, abi.encode( _arg1, _arg2 ));
//         bytes32 creation_hash	= keccak256(
//             abi.encodePacked( bytes1( 0xff ), address( this ), _salt, keccak256( creation ))
//         );
//         return address( uint160( uint256( creation_hash )));
//     }
//
// In Python using Web3, we could call this (view) contract function, or we can Contract creation encoded using the ABI:
//  
//  creation_code		= ContractName.constructor( arg1, arg2 ).data_in_transaction;
//  
// 
import "openzeppelin-contracts/contracts/interfaces/IERC20.sol";

contract ForwarderERC20 {
  constructor( address payable _recipient, IERC20[] memory _tokens ) public payable {
      for (uint256 tok = 0; tok < _tokens.length; tok++) {
          uint256 tok_balance;
          // Get the balance of the contract for the current token
          try _tokens[tok].balanceOf( address( this )) returns ( uint256 value ) {
              tok_balance = value;
          } catch {
              continue;
          }
          if ( tok_balance > 0 ) {
              // Forward the balance to the recipient
              try _tokens[tok].transfer( _recipient, tok_balance ) returns ( bool ) {
                  // ignore failing ERC-20 transfer
              } catch {
                  continue;  // ignore exception on ERC-20 transfer
              }
          }
      }
      selfdestruct( _recipient );
   }
}
