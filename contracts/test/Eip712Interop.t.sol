// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {Test} from "forge-std/Test.sol";
import {ProofOfKnowledge} from "../src/ProofOfKnowledge.sol";

/**
 * @notice Pins the EIP-712 encoding that blockchain/chain.py signs against.
 *
 * @dev The off-chain agent builds its typed data with eth-account, entirely
 * independently of this contract. If the type string, field order, or field
 * types drift apart, every signature the agent produces starts recovering to
 * the wrong address and every submission reverts with UnauthorisedAttestor,
 * with nothing to indicate why.
 *
 * These tests recompute the encoding from the literal EIP-712 spec rather than
 * reusing the contract's own constants, so a typo in the contract cannot hide
 * behind itself.
 *
 * The digest below was cross-checked byte for byte against
 * eth_account.messages.encode_typed_data for the same inputs.
 */
contract Eip712InteropTest is Test {
    ProofOfKnowledge pok;

    function setUp() public {
        pok = new ProofOfKnowledge(address(0xBEEF));
    }

    /// @dev Must match the "ReviewProof" entry in _sign_attestation's `types`.
    function testProofTypeStringMatchesThePythonSigner() public view {
        bytes32 expectedTypeHash = keccak256(
            "ReviewProof(address learner,bytes32 lessonHash,uint8 score,uint8 level,bytes32 sessionId)"
        );

        address learner = address(0x3333);
        bytes32 lesson = keccak256("lesson");
        bytes32 session = keccak256("session");
        uint8 score = 3;
        uint8 level = 2;

        bytes32 structHash =
            keccak256(abi.encode(expectedTypeHash, learner, lesson, score, level, session));
        bytes32 expectedDigest =
            keccak256(abi.encodePacked("\x19\x01", pok.domainSeparator(), structHash));

        assertEq(
            pok.hashProof(learner, lesson, score, level, session),
            expectedDigest,
            "contract type string drifted from the off-chain signer"
        );
    }

    /// @dev Must match the "domain" dict in _sign_attestation.
    function testDomainFieldsMatchThePythonSigner() public view {
        bytes32 expected = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256(bytes("ProofOfKnowledge")), // domain.name
                keccak256(bytes("1")), // domain.version
                block.chainid,
                address(pok)
            )
        );
        assertEq(pok.domainSeparator(), expected);
    }

    /// @dev A signature built exactly the way the Python signer builds it, then
    /// packed r||s||v the way eth-account returns it, must be accepted.
    function testSignatureBuiltTheOffChainWayIsAccepted() public {
        uint256 key = 0xA11CE;
        address signer = vm.addr(key);

        ProofOfKnowledge fresh = new ProofOfKnowledge(signer);

        address learner = address(0x3333);
        bytes32 lesson = keccak256("lesson");
        bytes32 session = keccak256("session");

        bytes32 digest = fresh.hashProof(learner, lesson, 3, 2, session);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        bytes memory signature = abi.encodePacked(r, s, v); // eth-account layout

        fresh.submitProof(learner, lesson, 3, 2, session, signature);

        assertEq(fresh.getProofCount(learner), 1);
    }
}
