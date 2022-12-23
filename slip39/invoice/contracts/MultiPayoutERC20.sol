// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import {
    IERC20,
    MultiPayoutERC20Base
} from "contracts/MultiPayoutERC20Base.sol";

import {
    MultiPayoutERC20Forwarder
} from "contracts/MultiPayoutERC20Forwarder.sol";

/*
 * MultiPayoutERC20
 *
 * Disburses any ETH / ERC-20 (predefined) tokens to a predetermined set of recipients, proportionally.
 *
 * Product Fee Distribution
 * ------------------------
 *
 *     Guarantees that any ETH / ERC-20 tokens paid are distributed in a predetermined proportion to
 * a fixed set of recipients.
 *
 *
 * Single Use Address "Forwarder"
 * ------------------------------
 *
 * Collect ETH/ERC-20 tokens from a single Client, either to the Product's Fee Distribution Contract
 * address, using a delegated function in MultiPayoutERC20Base for efficiency.
 *
 *     In most situations, we would want to create payment addresses for each client, for which nobody
 * has the private key -- these addresses may *only* be used to deposit ERC-20 / ETH funds, which then
 * *must* be distributed according to the rules of the Contract (the code for which is known in
 * advance, and the disbursement rules therefore immutable).
 *
 *     With a certain Contract creator source address (the owner of the product), predefined salt
 * (unique per client) and Contract bytecode, the final Contract address is deterministic and
 * predictable.  You can make a "one-shot" MultiPayoutERC20Forwarder Contract that flushes its ERC-20 +
 * ETH contents to the specified recipient address(es) and then self-destructs.  This Smart Contract
 * may be constructed, funded, executed and selfdestructed in a single invocation (multiple times).
 * This allows single-use pseudo-random source addresses to be issued to each client, which can *only*
 * collect payment(s).
 *
 *     This Smart Contract is created and compiled (fixing the predefined recipients and their
 * fractional allocation of all ETH and any ERC-20's).  Then, the (eventual) address of this deployed
 * contract is computed:
 *
 *     https://forum.openzeppelin.com/t/guide-to-using-create2-sol-library-in-openzeppelin-contracts-2-5-to-deploy-a-vault-contract/2268
 *
 * To minimize Gas usage, attempts to follow the principles outlined in:
 *
 *     https://0xmacro.com/blog/solidity-gas-optimizations-cheat-sheet/
 *     https://yos.io/2021/05/17/gas-efficient-solidity/
 *     https://consensys.net/blog/developers/solidity-best-practices-for-smart-contract-security/
 */
contract MultiPayoutERC20 is MultiPayoutERC20Base {

    /*
     * Confirm/Assign that the given <data> is associated with the provided <salt>, reporting a Forwarder(<salt>)
     */
    mapping( uint256 => bytes32 ) private _salt_data;

    error ForwarderMismatch( uint256 salt );		// The Forwarder has already been allocated w/ different <data>

    event UpstreamPayout( address multipayout );	// Another MultiPayoutERC20 links us as a payee

    function upstream(
        address 		multipayout
    )
        external
    {
        emit UpstreamPayout( multipayout );
    }

    event ForwarderAssign( uint256 indexed salt, bytes32 data );// Someone has uniquely allocated a certain Forwarder address
    event ForwarderReport( uint256 indexed salt );		// Someone is reporting using a certain Forwarder address
    event ForwarderEngage( uint256 indexed salt );		// Someone executed a certain Forwarder

    /*
     * Confirm/assign _salt/_data
     *
     * When a non-zero _data is provided, emits a Forwarder(<salt>) event to inform the MultiSendERC20
     * owner that a new, arbitrary _salt has been used.  The address should be computed, so future
     * payments to the contract address may be harvested via .forwarder(<salt>).
     * 
     * Only if both are bytes32(0), would a zero _data be allowed; ie. no legitimate non-zero data can
     * be overridden by a bytes32(0).  If a bytes32(0) data is supplied for a previously valid non-zero
     * _salt/_data, we'll revert with a ForwarderMismatch.  This prevents two independent agents
     * deployed with the same agent ID (eg. Ed25519 signing key) but different eg. Machine ID from
     * using the same client payment address -- the first one to send an ETH payment to the
     * .forwarder{,_assign}(<salt>,<data>) and assign the associated _data succeeds; the subsequent
     * attempt to pay to the .forwarder{,_assign} w/ the same <salt> but different data will revert,
     * rejecting (refunding) the client's payment.
     * 
     * This allows a completely decentralized Licensing payment workflow; no central management of A)
     * allocating unique client payment addresses, and B) ensuring only a single client pays to an
     * address.  Of course, your product may implement a centrally managed workflow for allocating
     * client addresses uniquely, without going to the extra expense of storing/confirming the _data.
     * 
     * 
     * In both centralized and decentralized models, the author's payment processing system must
     * monitor their MultiPayoutERC20 contract's events for Forwarder{Assign,Report} events, and
     * compute the corresponding client addresses (in addition to any client addresses from <salt>s
     * generated by their centralized payment processing system).  When payments are seen arriving at
     * those addresse, they must be prepared to A) issue any licenses or other correspondence with the
     * client, and B) eventually trigger the .forwarder(<salt>).
     * 
     * Downstream payees (either directly into their Externally Owned Account, or via downstream
     * MultiPayoutERC20 contracts) have the option to monitor payments arriving at upstream contracts.
     * Whenever an UpstreamPayout event is generated, the payment system can begin to (also) monitor
     * the upstream contract's Forwarder{Assign,Report}(<salt>) events, and confirm that (eventually)
     * they are distributed via someone triggering upstream.forwarder(<salt>); if not collected
     * promptly, you have the option of collecting (your portion) of those payments, too.
     * 
     * The set different between Forwarder{Assign,Report}(<salt>) and ForwarderEngage(<salt>) yields
     * the set of reported <salt> values not yet collected.  Of course, if the upstream system keeps
     * additional unreported <salt> values allocated by its own internal systems, these will be
     * unknown.
     * 
     * A good convention to follow for centrally allocated client addresses would be to allocated them
     * using <salt> values numerically increasing from 0; then, anyone can efficiently precompute the
     * first few thousand addresses and check them as well, from time to time.
     */
    function _confirm_salt_data(
         uint256		_salt,
         bytes32		_data
    )
        private
    {
        bytes32 salt_data		= _salt_data[_salt];
        if ( salt_data != _data ) {
            if ( salt_data == bytes32( 0 )) {
                _salt_data[_salt]	= _data;  // must be non-zero.
                emit ForwarderAssign( _salt, _data );
            } else {
                revert ForwarderMismatch( _salt );
            }
        }
    }

    /*
     * Confirms/assigns _salt/_data -- NOTE: This MAY make state changes
     */
    modifier assignSaltData(
         uint256		_salt,
         bytes32		_data
    ) {
        _confirm_salt_data( _salt, _data );
        _;
    }

    /*
     * Reports intention to use _salt
     */
    modifier reportSalt(
         uint256		_salt
    ) {
        _;
    }

    event PayoutETH(   uint256 indexed value, address indexed to, bool indexed sent );
    event PayoutERC20( uint256 indexed value, address indexed to, bool indexed sent, IERC20 token );

    /*
     * constructor
     *
     * This is created via standard contract creation transactions, so the address is a hash of the
     * creator's address + transaction nonce.  It will therefore be globally unique.  If we did create
     * this from another contract (using the EVM CREATE2 opcode), then for each set of identical
     * ERC-20s passed, we would need to use a unique CREATE2 salt value -- or the resultant Contract
     * address would be duplicated.  So, since we do not use CREATE2, we do not need to pass anything
     * to make the construction bytecode unique.
     *
     * Since ERC-20s are dynamic, we'll make them an array.  Since the payees / fractions are static,
     * we'll pass them textually as part of the contract code.  This is unlike the
     * openzeppelin-contracts/contracts/finance/PaymentSplitter.sol, which allows dynamic modification
     * of payees, their shares and the ERC-20 tokens supported -- and only supports "Pull" payment from
     * payees.
     *
     * We do "Push" payments (accessibly by anyone), so the payee can obtain their fees whenever they like,
     * protected by nonRentrant to ensure a hostile ERC-20 cannot re-trigger payout to inflate their share.
     *
     * Caller's address is required so that identical contracts (same payouts, ERC-20 tokens) are unique,
     * if multiple addresses instantiate them w/ the same nonce.
     */
    struct PayeeReserve {			// bits
        address payable		payee;		// 160  payee address
	uint16			reserve;	//  16  [0,1) fixed-point remainder with 2^16 demonimator
     // bytes10			percent;	//  80  " 65.43210%"
    }						// ---
    PayeeReserve[] public	payees;		// 256 bits per record 

    /*
     * The CREATE2 contract address precomputation requires the hash of the constructor abi call to the
     * ...Forwarder.  This is all known at MultiPayoutERC20 comstructor runtime time, so can be computed
     * and placed in an immutable.
     */
    bytes32 public immutable	forwarder_hash	= keccak256(
	abi.encodePacked(
	    type( MultiPayoutERC20Forwarder ).creationCode,
	    abi.encode( address( this ))
	)
    );

    constructor(
       PayeeReserve[] memory	_payees,
       IERC20[] memory		_erc20s
    )
       MultiPayoutERC20Base( _erc20s )
       payable
    {
	// require( _payees.length > 0 );			// At least one payee (will underflow in next test)
	require( _payees[_payees.length-1].reserve == 0 );	// Full payout required; remaining balance to last payee

	for ( uint256 p = 0; p < _payees.length; p++ ) {
	    payees.push( _payees[p] );
	    /*
	    try MultiPayoutERC20( _payees[p].payee ).upstream( address( this )) {
                // The downstream payee is a MultiPayoutERC20, an UpstreamPayout event allowing its
	        // users and payees to monitor this MultiPayoutERC20 contract for new client payments.
	    } catch {
	        // Not a MultiPayoutERC20; ignore.
	    }
  	    */
	}
    }

    /*
     * forwarder...( <salt> [,<data>] )
     *
     * Anyone can instantiate a forwarder; it can only forward the client's ETH/ERC-20 tokens to this
     * very contract.  So: fill your boots.  So long as the ERC-20 tokens supported by this Contract
     * are only settable by the Owner, it is designed to be safe for anyone to invoke.
     *
     * By convention, forwarder <salt> values allocated logically (ie. by your billing system) are
     * assumed to start at uint256( 0 ) and count up.  It is up to you to ensure you don't re-use the
     * same salt for multiple clients.  Just remember the address, and monitor it for incoming payment.
     *
     * If your client doesn't wish to use your billing system, they may allocate their own client
     * account payment address.  These are assumed to be arbitrary random uint256 <salt> values (usually,
     * derived from some unique client-specific data, like an Ed25519 public key).
     *
     * Any agent (eg. a custodial exchange wallet withdrawal) may pay the required cryptocurrency into
     * any allocated client account.
     *
     * However, at some point, either your billing system (if you're issuing the Licenses), or the
     * client itself (if it is self-provisoning the License) must invoke MultiPayoutERC20's
     * .forwarder(<salt>[,<data>]).  This uniquely and atomically associates the client's _salt with a
     * bytes32 _data -- and forwards the payment to your product's MultiPayoutERC20 contract.  An ETH
     * payment can (also) be sent to this call, simultaneously paying for and allocating the License.
     * If desired, a call to MultiPayoutERC20.forwarder_address(_salt,_data ) can also uniquely and
     * atomically allocate the address and associate _salt/_data.  Then, ETH or ERC-20s can be safely
     * transferred, and a later (more expensive) call to .forwarder(_salt) can be made (by anyone).
     *
     * There are always ways to game such a system.  However, so long as the client software's license
     * checking code isn't defeated, or it isn't run in a client environment that always returns a
     * predermined Machine ID and Ed25519 prvkey/pubkey), then the licensing checking will be atomic
     * (no 2 clients can accidentally allocate and pay into the same ...Forwarder contract address)
     * and reliable (the blockchain can be queried to determine that payment had been received to the
     * ...Forwarder contract).
     * 
     * We are checking licensing for clients: not thieves that purposely run an altered product.
     */

    /*
     * Create and returns the ...Forwarder contract's address for <salt>, paying any <msg.value> thru
     * 
     * The ...Forwarder contract clears out its contract address, forwarding all ETH + ERC-20s into
     * this MultiPayoutERC20 contract.  The msg.value *could* simply be left in the MultiPayoutERC20
     * -- but, then it would *not* show as having been paid through the ...Forwarder contract address
     * as part of the transaction.  A simple Licensing check *requires* that a query of the client's
     * Forwarder contract address contains a payment.
     *
     * May be used with any <salt> whatsoever, "allocated" or not:
     *
     * Someone could collect the Forwarder(<salt>) events from all transactions on this contract,
     * compute all the possible addresses, check them for non-zero values, and execute the
     * .forwarder(<salt>) for each one containing any ETH/ERC-20 value.  For example, one of the
     * payees of the MultiPayoutERC20 contract(s) who wishes to collect their portion of the
     * contract's revenue could do it.
     *
     * Alternatively, an accounting system could determine to use a numeric sequence of <salt> values
     * eg. 0, 1, 2, 3, ..., precompute the ...Forwarder contract addresses, and never invoke
     * .forwarder(<salt>,<data>) or .forwarder_address(<salt>,<data>) to inform the MultiPayoutERC20
     * contract that such addresses are "in play" via Forwarder(<salt>) events.  Later, when some
     * address receives funds, the accounting system could detect this and invoke the
     * .forwarder(<salt>) to collect the funds -- never allocating a _salt/_data for the address (and,
     * presumably, accomplishing any client License detection some other way, or not at all).
     *
     * WARNING
     *
     * It is your client software's responsibility to use one (or both) of these approaches consistenly!
     * If you issue invoices containing addresses using <salt> that have not been associated w/ <data>,
     * you will have to remember this fact outside of MultiPayoutERC20.
     */
    function forwarder(
         uint256		_salt
    )
        public			// Callable externally and internally
        payable			// May include a non-zero ETH msg.value
        notDelegated		// Does not allow creation of MultiPayoutForwarder w/ any other address( this ) value
        returns ( address, bytes32 )
    {
        emit ForwarderEngage( _salt );
        return (
            address( new MultiPayoutERC20Forwarder{
                salt:	bytes32( _salt ),		// CREATE2 opcode requires salt
                value:	msg.value			// Any msg.value is passed to ...Forwarder
            }( payable( address( this )))),		// ...Forwarder constructor requires this contract's address
            _salt_data[_salt]				// And return the _data associated with _salt (if any)
        );
    }

    /* 
     * Checks (or assigns) _salt/_data, creates Forwarder for _salt and returns its address, paying any msg.value thru
     * 
     * A single call can be used to:
     * - Uniquely and atomically allocate a ...Forwarder address to a _salt, storing the client _data
     * - Pay a sum of ETH through the ...Forwarder contract, noting the payment in the blockchain
     *
     * This forms the foundation of a simple and reliable Licensing scheme.   Determine the license required
     * and the <ETH payment> required for it.  To check Licensing:
     *
     * - Query the Machine ID
     * - Create/load the client's Ed25591 signing prvkey/pubkey
     * - Sign the Machine ID using the prvkey; use 32-byte pubkey as uint256 _salt
     * - Take 256 bits of (or hash) the signature to use as bytes32 _data
     * - Invoke MultiPayoutERC20.forwarder_address( _salt ) to get (<address>, salt_data )
     *   - If salt_data == _data, and if <address> was paid the required ETH/ERC-20 value
     *     - Consider the product successfully licensed!
     *
     * If not yet licensed, query user to connect their wallet to proceed with Licensing:
     * - Use Web3 to sign and send a MultiPayoutERC20.forwarder{ value: <ETH payment>}( _salt, _data ) call
     *   - If successful,
     *     - Consider the product successfully paid and licensed!
     * 
     * Othewise, fail Licensing check.
     */
    function forwarder(
         uint256		_salt,
         bytes32		_data
    )
        external		// Callable externally only
        payable			// May include a non-zero ETH msg.value
        assignSaltData( _salt, _data ) // Guarantees _salt/_data are consistent
        returns ( address, bytes32 )
    {
        return forwarder( _salt );
    }

    /*
     * forwarder_address(<salt>)
     *
     * Returns the Forwarder contract address for _salt
     *
     * Useful for computing the pre-defined CREATE2 contract address for the specified <salt>
     *
     * Since all data required is either constant, provided by the arguments, or stored in immutable state
     * variables, this is a pure function.  D
     */
    function forwarder_address(
        uint256			_salt
    )
        public			// Callable externally and internally
        view			// No contract state changed (immutables not considered pure, unfortunately)
        returns ( address )
    {
        bytes32 create2_hash	= keccak256(
            abi.encodePacked( bytes1( 0xff ), __SELF, bytes32( _salt ), forwarder_hash )
        );
        return address( uint160( uint256( create2_hash )));
    }

    /*
     * forwarder_allocate(<salt>[,<data>])
     *
     * Returns the Forwarder contract address for _salt, and report any _salt/_data
     */
    function forwarder_allocate(
        uint256			_salt
    )
        external		// Callable externally only
	returns ( address, bytes32 )
    {
        emit ForwarderReport( _salt );
	return (forwarder_address( _salt ), _salt_data[_salt]);
    }

    /*
     * Checks (or assigns) the _salt/_data, returning the Forwarder contract address for _salt and _data
     */
    function forwarder_allocate(
        uint256			_salt,
        bytes32			_data
    )
        external		// Callable externally only
        assignSaltData( _salt, _data )
        returns ( address, bytes32 )
    {
        return (forwarder_address( _salt ), _salt_data[_salt]);
    }

    /*
     * value_except -- Compute the value, less a certain fraction reserved.
     *
     * The _reserve is an N-bit fixed-point value with a denominator 2^N, so can only represent values
     * in the range: (0,(2^N-1)/(2^N)), or fractionally: (0,1].  Assumes that this numerator is very
     * small vs. the size of the _value.
     *
     * This assumption is almost universally true, when the value is an amount of ETH or ERC-20
     * tokens, which have large very denominators.  For example, ETH is denominated in 10^18 WEI.  So,
     * when transferring .001 ETH, the _value in this calculation will be 10^15, or
     * 1,000,000,000,000,000.  Therefore, we will normally divide by the denominator *before*
     * multiplying by the numerator -- the opposite of what we would want to do to maintain precision.
     * However, if we detect that the _value is very large (there are 1-bits within the top N bits of
     * the _value), we will do scaling in the opposite order.
     *
     * This allows us to avoid overflow (the _reserved numerator < 2^N, which *must* be the case).
     */
    function value_except(
        uint256			_value,
        uint16			_reserve		// fixed-point (0,1] w/ denominator 2^16
    )
        private
        pure			// No contract state changed or read
        returns ( uint256 )
    {
        unchecked {
            if (( _value >> ( 256 - 16 )) > 0 ) {
                // Degenerate case: 1-bits in the top 16 bits of _value.  Loses precision in low bits,
                // but maintains precision (and avoids overflow) for large values.
                return _value - (( _value >> 16 ) * _reserve );
            } else {
                // Normal case: upper N bits of _value are empty; Maintains precision in low bits (no overflow).
                return _value - (( _value * _reserve ) >> 16 );
            }
        }
    }

    /*
     * transfer_ERC20_except -- transfer this ERC-20 token (if any) into 'to', reserving a proportion.
     *
     * ERC-20 .transfer call uses its msg.sender as from (ie. this contract address)
     */
    function transfer_ERC20_except(
        IERC20			_erc20,
        address payable		_to,
        uint16			_reserve		// fixed-point (0,1] w/ denominator 2^16
    )
        private
        returns (bool, uint256)  // true iff successful, and any ERC-20 token amount transferred
    {
        uint256 tok_balance;
        try _erc20.balanceOf( address( this )) returns ( uint256 balance ) {
            if ( balance > 0 ) {
                uint256 value		= value_except( balance, _reserve );
                try _erc20.transfer( _to, value ) returns (bool sent) {
                    return (sent, value );		// Success/failure transferring tok_value
                } catch {
                    return (false, value );		// Exception, trying to transfer tok_value
                }
            }
        } catch {
            return (false, 0);				// Exception, unknown ERC-20 amount
        }
        return (true, 0);				// Successful, but nothing to transfer
    }

    /*
     * Transfer all but reserve fraction of ERC-20s and ETH into 'to'.
     *
     * Execute the final ETH transfer if *any* ERC-20 token(s) moved, even if the value is 0
     * ETH.  This will trigger any subsidiary MultiPayoutERC20 contract to (also) payout.
     *
     * It is possible to use a large amount of gas, if many MultiPayoutERC20 contracts are
     * chained together, and many ERC-20 tokens are involved.  If the global gas limit is
     * exceeded, remove some supported ERC-20 tokens (temporarily) and try again.
     */
    function transfer_except(
        address payable		_to,
        uint16			_reserve		// fixed-point (0,1] w/ denominator 2^16
    )
        private
    {
        bool erc20s_sent		= false;
	uint256 erc20s_end		= erc20s.length;
        for ( uint256 t = 0; t < erc20s_end; ++t ) {
            IERC20 token		= erc20s[t];
            (bool tok_sent, uint256 tok_value) = transfer_ERC20_except( token, _to, _reserve );
            if ( tok_value > 0 ) {
                emit PayoutERC20( tok_value, _to, tok_sent, token );
                if ( tok_sent ) {
                    erc20s_sent = true;  // We successfully sent some ERC-20 tokens into '_to'
                }
            }
        }
        uint256 eth_balance		= address( this ).balance;
        if ( eth_balance > 0 || erc20s_sent ) {
            // Some ETH and/or ERC-20s sent into '_to'; trigger its receive!  If it's another
            // MultiPayoutERC20, this will trigger its own payout (even if passed ETH value is 0).
            uint256 eth_value		= value_except( eth_balance, _reserve );
            (bool eth_sent, )  		= _to.call{ value: eth_value }( "" );
            emit PayoutETH( eth_value, _to, eth_sent );
        }
    }

    /*
     * Anyone may invoke the payout API via receive(), resulting in all ETH and predefined ERC-20 tokens being
     * distributed as determined at contract creation.
     *
     * REENTRANCY ATTACK
     * 
     * In theory, an "attacker" MultiPayoutERC20-compatible contract could be constructed using
     * CREATE2, so its (eventual) address could be precomputed. Then, a sequence of one or more other
     * MultiPayoutERC20 contracts could use this address as a payee.  Finally, a "loop" would be
     * created by instantiating the "attacker" MultiPayoutERC20 at the originally precomputed address,
     * and indicating one or more of the other pre-existing MultiPayoutERC20s as a payee.
     * 
     * We cannot prevent this from happening, but we ensure it doesn't "lock up" the system, by detecting
     * reentrancy in the receive() function, and enforcing nonReentrant in the payout().  Thus, since
     * subsequent payees are paid via call( "" ) to their receive() functions, a loop simply short-circuits
     * at the first detection of the loop, and carries on with the remainder of its payees.
     * 
     * So, the "attacker" contract has now inserted itself in the payee processing tree of the
     * legitimate contracts, by convincing someone to set up a MultiPayoutERC20 with their address as
     * a payee.  This could be any legitimate-looking payee for some component of your product; the
     * owner of some sub-module of your product, for example.  The address they give you appears to be
     * a an Externally Owned Account (an EOA, which has no contract), so you cannot detect this
     * exploit in advance.
     *
     * You can safely trigger .forwarder(<salt>) calls, to collect your client's payments into your
     * MultiPayoutERC20, since they use IERC20.transfer for ERC-20s (which do not trigger additional
     * functionality in your contract), and selfdestruct for delivering the ETH (which also doesn't
     * trigger receive()).  However, when you later attempt to invoke a call("") to your receive()
     * function to distribute any collected funds, as soon as you (or a downstream MultiPayoutERC20
     * contract) invokes the "attacker", it calls back into some contract in the loop.  It receives
     * only its correct allocation of ERC-20 tokens from you, and (finally) its allocation of ETH to its
     * receive() function, triggering its own payout().
     *
     * The attacker hopes to loop around and re-invoke distribution to itself -- but we check for
     * reentrancy in receive() and DO NOTHING, instead.  The "attacker" contract probably doesn't
     * distribute any funds (its goal would probably be to keep all funds received, and send them to
     * some EOA under control of "attacker".)  So, avoiding another recursive invocation of payout()
     * prevents another tranche of fees being paid to the attacker (or anyone else paid before the
     * attacker's address), while allowing subsequent payout calls to succeed.
     *
     * DENIAL OF SERVICE
     *
     * A faulty/hostile ERC-20 token contract could consume Gas on each transfer, denying service
     * to the MultiPayoutERC20 Forwarder or .payout, but is easily solved by removing the ERC-20
     * using .erc20s_del( <token> ).
     *
     * A hostile contract with an expensive receive() function placed at any payee address is a greater
     * risk.  With CREATE2, it is impossible to prevent this -- unless your payees prove that they hold
     * the private key corresponding to the addresss.  However, we do want to allow linking
     * MultiPayoutERC20 contracts into downstream contracts.
     * 
     * Since the payees of your MultiPayoutERC20 contract are fixed and immutable, properly vetting the
     * payees, and getting offline proof of ownership of the signing keys (eg. by signing a note or
     * other transaction on the address), or observing the presence of a valid MultiPayoutERC20
     * contract at the payee address should be sufficient.
     */ 
    function payout()
        public			// Callable externally and internally
	nonReentrant
    {
        for ( uint256 p = 0; p < payees.length; ++p ) {
    	    transfer_except( payees[p].payee, payees[p].reserve );
    	}
    }

    /*
     * Processing incoming payments:
     *
     *     Which function is called, fallback() or receive()?
     *
     *             send Ether
     *                 |
     *          msg.data is empty?
     *                / \
     *             yes   no
     *             /       \
     * receive() exists?  fallback()
     *          /   \
     *       yes     no
     *       /         \
     *    receive()   fallback()
     *
     * NOTE: we *can* receive ETH without processing it here, via selfdestruct(); any later call
     * (even with a 0 value) will trigger payout.  Since the .forward( N ) contract uses
     * selfdestruct to collect ETH, no payout will be run on a standard incoming client payment.
     *
     * This contract is designed to allow any downstream payout recipient to execute the
     * payout function, as simply as possible.  Thus, we have a falback function, that reverts,
     * and a fallback function that executes the payout().  Thus, any incoming ETH
     * transfer to the contract (except via selfdestruct) will attempt to run payout.
     *
     * So, any wallet which can specify a high gas limit for a call("") transaction may be used.
     * Just transfer 0 ETH to the contract, and set a high gas limit (to allow for all the
     * payout proportion calculations and any ERC-20 transfers to each payout recipient).  Using
     * .send/.transfer will not work, due to the low gas limit.
     */
    receive()
        external
        payable
    {
        if ( ! _reentrancyGuardEntered() ) {
            payout();
	}
    }

    fallback()
        external
        payable
    {
        revert();
    }

}
