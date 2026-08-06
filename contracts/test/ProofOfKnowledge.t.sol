// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {Test, console} from "forge-std/Test.sol";
import {ProofOfKnowledge} from "../src/ProofOfKnowledge.sol";

contract ProofOfKnowledgeTest is Test {
    ProofOfKnowledge pok;

    uint256 attestorKey = 0xA11CE;
    uint256 rogueKey = 0xBADBAD;
    address attestor;
    address rogue;

    address owner = makeAddr("owner");
    address learner = makeAddr("learner");
    address otherLearner = makeAddr("otherLearner");
    address relayer = makeAddr("relayer");

    bytes32 constant LESSON = keccak256("lesson: EIP-712 typed data");
    bytes32 constant SESSION = keccak256("session-1");

    function setUp() public {
        attestor = vm.addr(attestorKey);
        rogue = vm.addr(rogueKey);

        vm.prank(owner);
        pok = new ProofOfKnowledge(attestor);
    }

    /* ---------------------------------------------------------------- helpers */

    function _sign(uint256 key, address who, bytes32 lesson, uint8 score, uint8 level, bytes32 session)
        internal
        view
        returns (bytes memory)
    {
        bytes32 digest = pok.hashProof(who, lesson, score, level, session);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(key, digest);
        return abi.encodePacked(r, s, v);
    }

    function _submit(address who, uint8 score, uint8 level, bytes32 session) internal {
        bytes memory sig = _sign(attestorKey, who, LESSON, score, level, session);
        vm.prank(relayer);
        pok.submitProof(who, LESSON, score, level, session, sig);
    }

    /* ------------------------------------------------------------- deployment */

    function testConstructorSetsOwnerAndAttestor() public view {
        assertEq(pok.owner(), owner);
        assertTrue(pok.isAttestor(attestor));
        assertFalse(pok.isAttestor(rogue));
    }

    function testConstructorRejectsZeroAttestor() public {
        vm.expectRevert(ProofOfKnowledge.ZeroAddress.selector);
        new ProofOfKnowledge(address(0));
    }

    /* ------------------------------------------------------ the identity fix */

    /// @dev The bug this redesign exists to fix. The relayer submits, but the
    /// proof must land on the learner named in the signature, not on the
    /// address that paid gas.
    function testProofIsCreditedToLearnerNotRelayer() public {
        _submit(learner, 3, 2, SESSION);

        assertEq(pok.getProofCount(learner), 1, "learner credited");
        assertEq(pok.getProofCount(relayer), 0, "relayer not credited");
        assertEq(pok.getProofCount(attestor), 0, "attestor not credited");
    }

    function testDistinctLearnersKeepSeparateHistories() public {
        _submit(learner, 4, 1, keccak256("s1"));
        _submit(otherLearner, 2, 3, keccak256("s2"));
        _submit(learner, 2, 1, keccak256("s3"));

        assertEq(pok.getProofCount(learner), 2);
        assertEq(pok.getProofCount(otherLearner), 1);
        assertEq(pok.totalScore(learner), 6);
        assertEq(pok.totalScore(otherLearner), 2);
    }

    function testAnyoneCanRelayAValidAttestation() public {
        bytes memory sig = _sign(attestorKey, learner, LESSON, 3, 2, SESSION);

        vm.prank(makeAddr("randomStranger"));
        pok.submitProof(learner, LESSON, 3, 2, SESSION, sig);

        assertEq(pok.getProofCount(learner), 1);
    }

    /* --------------------------------------------------------- authorisation */

    function testRejectsSignatureFromUnauthorisedSigner() public {
        bytes memory sig = _sign(rogueKey, learner, LESSON, 3, 2, SESSION);

        vm.expectRevert(
            abi.encodeWithSelector(ProofOfKnowledge.UnauthorisedAttestor.selector, rogue)
        );
        pok.submitProof(learner, LESSON, 3, 2, SESSION, sig);
    }

    function testRevokedAttestorCannotSubmitEvenWithOlderSignature() public {
        bytes memory sig = _sign(attestorKey, learner, LESSON, 3, 2, SESSION);

        vm.prank(owner);
        pok.setAttestor(attestor, false);

        vm.expectRevert(
            abi.encodeWithSelector(ProofOfKnowledge.UnauthorisedAttestor.selector, attestor)
        );
        pok.submitProof(learner, LESSON, 3, 2, SESSION, sig);
    }

    function testOwnerCanAddASecondAttestor() public {
        vm.prank(owner);
        pok.setAttestor(rogue, true);

        bytes memory sig = _sign(rogueKey, learner, LESSON, 1, 1, SESSION);
        pok.submitProof(learner, LESSON, 1, 1, SESSION, sig);

        assertEq(pok.getProofCount(learner), 1);
    }

    function testNonOwnerCannotSetAttestor() public {
        vm.prank(learner);
        vm.expectRevert(ProofOfKnowledge.NotOwner.selector);
        pok.setAttestor(rogue, true);
    }

    function testOwnershipTransfer() public {
        vm.prank(owner);
        pok.transferOwnership(learner);
        assertEq(pok.owner(), learner);

        vm.prank(learner);
        pok.setAttestor(rogue, true);
        assertTrue(pok.isAttestor(rogue));
    }

    function testTransferOwnershipRejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(ProofOfKnowledge.ZeroAddress.selector);
        pok.transferOwnership(address(0));
    }

    function testSetAttestorRejectsZero() public {
        vm.prank(owner);
        vm.expectRevert(ProofOfKnowledge.ZeroAddress.selector);
        pok.setAttestor(address(0), true);
    }

    /* ------------------------------------------------------ replay protection */

    function testSessionCannotBeReplayed() public {
        _submit(learner, 4, 2, SESSION);

        bytes memory sig = _sign(attestorKey, learner, LESSON, 4, 2, SESSION);
        vm.expectRevert(
            abi.encodeWithSelector(ProofOfKnowledge.SessionAlreadyUsed.selector, SESSION)
        );
        pok.submitProof(learner, LESSON, 4, 2, SESSION, sig);

        assertEq(pok.getProofCount(learner), 1, "count must not inflate");
        assertEq(pok.totalScore(learner), 4, "score must not inflate");
    }

    /// @dev A session id is global, so a captured signature cannot be re-aimed
    /// at a different learner either.
    function testSessionIsConsumedAcrossAllLearners() public {
        _submit(learner, 4, 2, SESSION);

        bytes memory sig = _sign(attestorKey, otherLearner, LESSON, 4, 2, SESSION);
        vm.expectRevert(
            abi.encodeWithSelector(ProofOfKnowledge.SessionAlreadyUsed.selector, SESSION)
        );
        pok.submitProof(otherLearner, LESSON, 4, 2, SESSION, sig);
    }

    function testSessionUsedFlagIsPublic() public {
        assertFalse(pok.sessionUsed(SESSION));
        _submit(learner, 3, 1, SESSION);
        assertTrue(pok.sessionUsed(SESSION));
    }

    /* -------------------------------------------------- signature tampering */

    /// @dev Every field is inside the signed struct, so a relayer that edits
    /// any of them recovers a different address and is rejected.
    function testTamperingWithAnyFieldInvalidatesTheSignature() public {
        bytes memory sig = _sign(attestorKey, learner, LESSON, 3, 2, SESSION);

        vm.expectRevert(); // learner swapped
        pok.submitProof(otherLearner, LESSON, 3, 2, SESSION, sig);

        vm.expectRevert(); // score inflated
        pok.submitProof(learner, LESSON, 4, 2, SESSION, sig);

        vm.expectRevert(); // level changed
        pok.submitProof(learner, LESSON, 3, 3, SESSION, sig);

        vm.expectRevert(); // lesson swapped
        pok.submitProof(learner, keccak256("other lesson"), 3, 2, SESSION, sig);

        vm.expectRevert(); // session swapped
        pok.submitProof(learner, LESSON, 3, 2, keccak256("other session"), sig);

        assertEq(pok.getProofCount(learner), 0);
    }

    function testRejectsMalformedSignatureLength() public {
        vm.expectRevert(
            abi.encodeWithSelector(ProofOfKnowledge.InvalidSignatureLength.selector, 64)
        );
        pok.submitProof(learner, LESSON, 3, 2, SESSION, new bytes(64));
    }

    function testRejectsBadV() public {
        bytes memory sig = _sign(attestorKey, learner, LESSON, 3, 2, SESSION);
        sig[64] = bytes1(uint8(29));

        vm.expectRevert(ProofOfKnowledge.InvalidSignatureV.selector);
        pok.submitProof(learner, LESSON, 3, 2, SESSION, sig);
    }

    /// @dev secp256k1 signatures are malleable: (r, s, v) and (r, n - s, v ^ 1)
    /// both recover the same signer. Without the upper-half s check, the same
    /// attestation would have two valid encodings.
    function testRejectsMalleableHighSSignature() public {
        bytes32 digest = pok.hashProof(learner, LESSON, 3, 2, SESSION);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(attestorKey, digest);

        uint256 n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;
        bytes32 flippedS = bytes32(n - uint256(s));
        uint8 flippedV = v == 27 ? 28 : 27;
        bytes memory malleable = abi.encodePacked(r, flippedS, flippedV);

        vm.expectRevert(ProofOfKnowledge.InvalidSignatureS.selector);
        pok.submitProof(learner, LESSON, 3, 2, SESSION, malleable);
    }

    /* ---------------------------------------------------------- input bounds */

    function testRejectsScoreOutOfRange() public {
        bytes memory sig = _sign(attestorKey, learner, LESSON, 5, 2, SESSION);
        vm.expectRevert(abi.encodeWithSelector(ProofOfKnowledge.ScoreOutOfRange.selector, 5));
        pok.submitProof(learner, LESSON, 5, 2, SESSION, sig);

        sig = _sign(attestorKey, learner, LESSON, 0, 2, SESSION);
        vm.expectRevert(abi.encodeWithSelector(ProofOfKnowledge.ScoreOutOfRange.selector, 0));
        pok.submitProof(learner, LESSON, 0, 2, SESSION, sig);
    }

    function testRejectsLevelOutOfRange() public {
        bytes memory sig = _sign(attestorKey, learner, LESSON, 3, 9, SESSION);
        vm.expectRevert(abi.encodeWithSelector(ProofOfKnowledge.LevelOutOfRange.selector, 9));
        pok.submitProof(learner, LESSON, 3, 9, SESSION, sig);

        sig = _sign(attestorKey, learner, LESSON, 3, 0, SESSION);
        vm.expectRevert(abi.encodeWithSelector(ProofOfKnowledge.LevelOutOfRange.selector, 0));
        pok.submitProof(learner, LESSON, 3, 0, SESSION, sig);
    }

    function testRejectsZeroLearner() public {
        bytes memory sig = _sign(attestorKey, address(0), LESSON, 3, 2, SESSION);
        vm.expectRevert(ProofOfKnowledge.ZeroAddress.selector);
        pok.submitProof(address(0), LESSON, 3, 2, SESSION, sig);
    }

    /* ---------------------------------------------------------------- storage */

    function testStoredProofRecordsEveryField() public {
        vm.warp(1_700_000_000);
        _submit(learner, 3, 4, SESSION);

        ProofOfKnowledge.ReviewProof memory p = pok.getProof(learner, 0);
        assertEq(p.lessonHash, LESSON);
        assertEq(p.score, 3);
        assertEq(p.level, 4);
        assertEq(p.timestamp, 1_700_000_000);
        assertEq(p.sessionId, SESSION);
        assertEq(p.attestor, attestor, "records which attestor vouched");
    }

    function testGetProofRevertsOutOfBounds() public {
        _submit(learner, 3, 1, SESSION);
        vm.expectRevert(
            abi.encodeWithSelector(ProofOfKnowledge.IndexOutOfBounds.selector, 1, 1)
        );
        pok.getProof(learner, 1);
    }

    function testEmitsProofSubmitted() public {
        bytes memory sig = _sign(attestorKey, learner, LESSON, 3, 2, SESSION);
        vm.warp(1_700_000_000);

        vm.expectEmit(true, true, true, true, address(pok));
        emit ProofOfKnowledge.ProofSubmitted(
            learner, SESSION, LESSON, 3, 2, 1_700_000_000, attestor
        );
        pok.submitProof(learner, LESSON, 3, 2, SESSION, sig);
    }

    /* ------------------------------------------------------------ pagination */

    function testPaginationReturnsRequestedWindow() public {
        for (uint256 i = 0; i < 5; i++) {
            _submit(learner, 2, 1, keccak256(abi.encode("s", i)));
        }

        ProofOfKnowledge.ReviewProof[] memory page = pok.getProofs(learner, 1, 2);
        assertEq(page.length, 2);
        assertEq(page[0].sessionId, keccak256(abi.encode("s", uint256(1))));
        assertEq(page[1].sessionId, keccak256(abi.encode("s", uint256(2))));
    }

    function testPaginationClipsAtTheEnd() public {
        for (uint256 i = 0; i < 3; i++) {
            _submit(learner, 2, 1, keccak256(abi.encode("s", i)));
        }
        assertEq(pok.getProofs(learner, 2, 100).length, 1, "clipped, not reverting");
        assertEq(pok.getProofs(learner, 3, 1).length, 0, "past the end is empty");
        assertEq(pok.getProofs(learner, 0, 0).length, 0);
    }

    /* --------------------------------------------------------------- averages */

    function testAverageIsZeroWithNoReviews() public view {
        assertEq(pok.getAverageScore(learner), 0);
    }

    /// @dev The old contract floor-divided, so 3 + 4 + 4 + 4 over 4 reviews
    /// reported 3 instead of 3.75. Scaling keeps the fraction.
    function testAverageKeepsTheFraction() public {
        _submit(learner, 3, 1, keccak256("a"));
        _submit(learner, 4, 1, keccak256("b"));
        _submit(learner, 4, 1, keccak256("c"));
        _submit(learner, 4, 1, keccak256("d"));

        assertEq(pok.getAverageScore(learner), 3.75e18);
    }

    /* ------------------------------------------------------------------- fuzz */

    function testFuzzValidAttestationAlwaysRecords(
        address who,
        bytes32 lesson,
        uint8 score,
        uint8 level,
        bytes32 session
    ) public {
        vm.assume(who != address(0));
        score = uint8(bound(score, 1, 4));
        level = uint8(bound(level, 1, 4));

        bytes memory sig = _sign(attestorKey, who, lesson, score, level, session);
        pok.submitProof(who, lesson, score, level, session, sig);

        assertEq(pok.getProofCount(who), 1);
        assertEq(pok.totalScore(who), score);
        assertTrue(pok.sessionUsed(session));
    }

    /// @dev No key other than an authorised attestor's can produce an
    /// acceptable signature, whatever the payload.
    function testFuzzOnlyAuthorisedKeysAreAccepted(
        uint256 wrongKey,
        uint8 score,
        uint8 level
    ) public {
        wrongKey = bound(wrongKey, 1, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364140);
        vm.assume(vm.addr(wrongKey) != attestor);
        score = uint8(bound(score, 1, 4));
        level = uint8(bound(level, 1, 4));

        bytes memory sig = _sign(wrongKey, learner, LESSON, score, level, SESSION);
        vm.expectRevert(
            abi.encodeWithSelector(
                ProofOfKnowledge.UnauthorisedAttestor.selector, vm.addr(wrongKey)
            )
        );
        pok.submitProof(learner, LESSON, score, level, SESSION, sig);
    }

    function testFuzzTotalScoreTracksSumOfSubmissions(uint8[10] memory rawScores) public {
        uint256 expected;
        for (uint256 i = 0; i < rawScores.length; i++) {
            uint8 score = uint8(bound(rawScores[i], 1, 4));
            _submit(learner, score, 1, keccak256(abi.encode("fuzz", i)));
            expected += score;
        }
        assertEq(pok.totalScore(learner), expected);
        assertEq(pok.getProofCount(learner), rawScores.length);
        assertEq(pok.getAverageScore(learner), (expected * 1e18) / rawScores.length);
    }

    /* -------------------------------------------------------------- EIP-712 */

    function testDomainSeparatorMatchesTheSpec() public view {
        bytes32 expected = keccak256(
            abi.encode(
                keccak256(
                    "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
                ),
                keccak256(bytes("ProofOfKnowledge")),
                keccak256(bytes("1")),
                block.chainid,
                address(pok)
            )
        );
        assertEq(pok.domainSeparator(), expected);
    }

    /// @dev A signature valid on one chain must not be replayable on another,
    /// which is what binding chainId into the domain buys.
    function testDomainSeparatorChangesWithChainId() public {
        bytes32 before = pok.domainSeparator();
        vm.chainId(999);
        assertTrue(pok.domainSeparator() != before, "domain must rebind on fork");
    }

    function testSignatureFromAnotherChainIsRejected() public {
        bytes memory sig = _sign(attestorKey, learner, LESSON, 3, 2, SESSION);
        vm.chainId(999);

        vm.expectRevert();
        pok.submitProof(learner, LESSON, 3, 2, SESSION, sig);
    }
}
