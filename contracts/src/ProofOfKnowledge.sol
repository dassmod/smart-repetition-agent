// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title ProofOfKnowledge
 * @author Dastan Modubash
 * @notice An on-chain record of spaced-repetition reviews, written by an
 * off-chain agent on a learner's behalf.
 *
 * @dev The problem this solves. The agent that grades a review runs off-chain,
 * and the learners it grades are Telegram users who hold no keys and pay no
 * gas. A naive design has the agent call `submitProof` directly and record
 * `msg.sender` as the learner, which collapses every learner in the system
 * onto the agent's single relayer address.
 *
 * Instead the agent acts as an *attestor*. It signs an EIP-712 typed
 * attestation naming the learner, and anyone may relay that signature on-chain.
 * The contract recovers the signer, checks it against the authorised attestor
 * set, and credits the proof to the named learner. Three properties follow:
 *
 * - Learner identity survives. Per-learner history and averages are real.
 * - The relayer is untrusted. It pays gas and can do nothing else; tampering
 *   with any field invalidates the signature.
 * - Attestations are single-use. Each `sessionId` is consumed on submission,
 *   so a captured signature cannot be replayed to inflate a learner's record.
 *
 * This is a testnet learning artifact, not audited production code.
 */
contract ProofOfKnowledge {
    /* ------------------------------------------------------------------ types */

    /// @notice One graded review, as recorded on-chain.
    /// @param lessonHash Hash of the lesson material reviewed.
    /// @param score FSRS rating the dialogue resolved to, 1 (again) to 4 (easy).
    /// @param level Difficulty tier the question was asked at, 1 to 4.
    /// @param timestamp Block timestamp at which the proof was recorded.
    /// @param sessionId Unique id of the review session; consumed once.
    /// @param attestor Attestor whose signature authorised this proof.
    struct ReviewProof {
        bytes32 lessonHash;
        uint8 score;
        uint8 level;
        uint256 timestamp;
        bytes32 sessionId;
        address attestor;
    }

    /* -------------------------------------------------------------- constants */

    uint8 public constant MIN_SCORE = 1;
    uint8 public constant MAX_SCORE = 4;
    uint8 public constant MIN_LEVEL = 1;
    uint8 public constant MAX_LEVEL = 4;

    /// @dev Average scores are returned scaled by this factor, because Solidity
    /// integer division would otherwise report a 3.75 average as 3.
    uint256 public constant AVERAGE_SCALE = 1e18;

    bytes32 private constant _EIP712_DOMAIN_TYPEHASH = keccak256(
        "EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    );

    bytes32 private constant _PROOF_TYPEHASH = keccak256(
        "ReviewProof(address learner,bytes32 lessonHash,uint8 score,uint8 level,bytes32 sessionId)"
    );

    /* ------------------------------------------------------------------ errors */

    error NotOwner();
    error ZeroAddress();
    error ScoreOutOfRange(uint8 score);
    error LevelOutOfRange(uint8 level);
    error SessionAlreadyUsed(bytes32 sessionId);
    error UnauthorisedAttestor(address recovered);
    error InvalidSignatureLength(uint256 length);
    error InvalidSignatureS();
    error InvalidSignatureV();
    error IndexOutOfBounds(uint256 index, uint256 length);

    /* ------------------------------------------------------------------- state */

    address public owner;

    /// @notice Addresses whose signatures the contract accepts as attestations.
    mapping(address => bool) public isAttestor;

    /// @notice Review history per learner, in submission order.
    mapping(address => ReviewProof[]) private _proofs;

    /// @notice Sum of scores per learner, used to derive averages without a loop.
    mapping(address => uint256) public totalScore;

    /// @notice Session ids already recorded. Enforces one proof per session.
    mapping(bytes32 => bool) public sessionUsed;

    /// @dev Cached at construction; rebuilt on the fly if the chain forks so a
    /// signature can never be replayed across chain ids.
    bytes32 private immutable _CACHED_DOMAIN_SEPARATOR;
    uint256 private immutable _CACHED_CHAIN_ID;

    /* ------------------------------------------------------------------ events */

    event ProofSubmitted(
        address indexed learner,
        bytes32 indexed sessionId,
        bytes32 indexed lessonHash,
        uint8 score,
        uint8 level,
        uint256 timestamp,
        address attestor
    );
    event AttestorSet(address indexed attestor, bool authorised);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    /* --------------------------------------------------------------- modifiers */

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    /* ------------------------------------------------------------- constructor */

    /// @param initialAttestor The agent's signing address. May be the deployer.
    constructor(address initialAttestor) {
        if (initialAttestor == address(0)) revert ZeroAddress();

        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);

        isAttestor[initialAttestor] = true;
        emit AttestorSet(initialAttestor, true);

        _CACHED_CHAIN_ID = block.chainid;
        _CACHED_DOMAIN_SEPARATOR = _buildDomainSeparator();
    }

    /* ------------------------------------------------------------------- admin */

    /// @notice Authorise or revoke an attestor. Revoking takes effect
    /// immediately, including for signatures created before the revocation.
    function setAttestor(address attestor, bool authorised) external onlyOwner {
        if (attestor == address(0)) revert ZeroAddress();
        isAttestor[attestor] = authorised;
        emit AttestorSet(attestor, authorised);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        if (newOwner == address(0)) revert ZeroAddress();
        emit OwnershipTransferred(owner, newOwner);
        owner = newOwner;
    }

    /* ------------------------------------------------------------- submission */

    /**
     * @notice Record a review proof for `learner`, authorised by an attestor's
     * EIP-712 signature. Callable by anyone; the caller only pays gas.
     * @param learner Address the proof is credited to.
     * @param lessonHash Hash of the reviewed material.
     * @param score FSRS rating, 1 to 4.
     * @param level Difficulty tier the question was asked at, 1 to 4.
     * @param sessionId Unique session id; reverts if already used.
     * @param signature EIP-712 signature over the above, from an attestor.
     */
    function submitProof(
        address learner,
        bytes32 lessonHash,
        uint8 score,
        uint8 level,
        bytes32 sessionId,
        bytes calldata signature
    ) external {
        if (learner == address(0)) revert ZeroAddress();
        if (score < MIN_SCORE || score > MAX_SCORE) revert ScoreOutOfRange(score);
        if (level < MIN_LEVEL || level > MAX_LEVEL) revert LevelOutOfRange(level);
        if (sessionUsed[sessionId]) revert SessionAlreadyUsed(sessionId);

        bytes32 digest = hashProof(learner, lessonHash, score, level, sessionId);
        address attestor = _recover(digest, signature);
        if (!isAttestor[attestor]) revert UnauthorisedAttestor(attestor);

        // Consume the session before writing, so a reentrant relayer cannot
        // double-record. No external calls follow, but the ordering is free.
        sessionUsed[sessionId] = true;

        _proofs[learner].push(
            ReviewProof({
                lessonHash: lessonHash,
                score: score,
                level: level,
                timestamp: block.timestamp,
                sessionId: sessionId,
                attestor: attestor
            })
        );
        totalScore[learner] += score;

        emit ProofSubmitted(
            learner, sessionId, lessonHash, score, level, block.timestamp, attestor
        );
    }

    /* ------------------------------------------------------------------- views */

    /// @notice Number of proofs recorded for a learner.
    function getProofCount(address learner) external view returns (uint256) {
        return _proofs[learner].length;
    }

    /// @notice Fetch a single proof by index.
    function getProof(address learner, uint256 index)
        external
        view
        returns (ReviewProof memory)
    {
        uint256 length = _proofs[learner].length;
        if (index >= length) revert IndexOutOfBounds(index, length);
        return _proofs[learner][index];
    }

    /// @notice Fetch a page of proofs. History is unbounded, so callers that
    /// read it on-chain must paginate rather than pull the whole array.
    /// @param start First index to return.
    /// @param count Maximum number of proofs to return; the result is clipped
    /// at the end of the array.
    function getProofs(address learner, uint256 start, uint256 count)
        external
        view
        returns (ReviewProof[] memory page)
    {
        uint256 length = _proofs[learner].length;
        if (start >= length) return new ReviewProof[](0);

        uint256 end = start + count;
        if (end > length) end = length;

        page = new ReviewProof[](end - start);
        for (uint256 i = start; i < end; i++) {
            page[i - start] = _proofs[learner][i];
        }
    }

    /// @notice Mean score for a learner, scaled by {AVERAGE_SCALE}.
    /// @dev Returns 0 for a learner with no reviews. Scaled because plain
    /// integer division reports a 3.75 average as 3.
    function getAverageScore(address learner) external view returns (uint256) {
        uint256 count = _proofs[learner].length;
        if (count == 0) return 0;
        return (totalScore[learner] * AVERAGE_SCALE) / count;
    }

    /* -------------------------------------------------------------- signatures */

    /// @notice The EIP-712 domain separator for this contract on this chain.
    function domainSeparator() public view returns (bytes32) {
        if (block.chainid == _CACHED_CHAIN_ID) return _CACHED_DOMAIN_SEPARATOR;
        return _buildDomainSeparator();
    }

    /// @notice The digest an attestor signs. Exposed so the off-chain agent and
    /// the tests derive it from the contract rather than reimplementing it.
    function hashProof(
        address learner,
        bytes32 lessonHash,
        uint8 score,
        uint8 level,
        bytes32 sessionId
    ) public view returns (bytes32) {
        bytes32 structHash = keccak256(
            abi.encode(_PROOF_TYPEHASH, learner, lessonHash, score, level, sessionId)
        );
        return keccak256(abi.encodePacked("\x19\x01", domainSeparator(), structHash));
    }

    function _buildDomainSeparator() private view returns (bytes32) {
        return keccak256(
            abi.encode(
                _EIP712_DOMAIN_TYPEHASH,
                keccak256(bytes("ProofOfKnowledge")),
                keccak256(bytes("1")),
                block.chainid,
                address(this)
            )
        );
    }

    /// @dev ECDSA recovery with malleability protection. Rejects the upper half
    /// of the s range and any v outside {27, 28}, so a single attestation has
    /// exactly one valid signature encoding.
    function _recover(bytes32 digest, bytes calldata signature)
        private
        pure
        returns (address)
    {
        if (signature.length != 65) revert InvalidSignatureLength(signature.length);

        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }

        if (uint256(s) > 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0) {
            revert InvalidSignatureS();
        }
        if (v != 27 && v != 28) revert InvalidSignatureV();

        address recovered = ecrecover(digest, v, r, s);
        if (recovered == address(0)) revert UnauthorisedAttestor(address(0));
        return recovered;
    }
}
