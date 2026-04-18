// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

contract ProofOfKnowledge {

    // --- Structs ---

    struct ReviewProof {
        bytes32 lessonHash;
        uint8 score;
        uint8 level;
        uint256 timestamp;
        bytes32 sessionId;
    }

    // --- State Variables ---

    address public owner;
    mapping(address => ReviewProof[]) public proofs;
    mapping(address => uint256) public reviewCount;
    mapping(address => uint256) public totalScore;

    // --- Events ---

    event ProofSubmitted(
        address indexed learner,
        bytes32 lessonHash,
        uint8 score,
        uint8 level,
        uint256 timestamp,
        bytes32 sessionId
    );

    // --- Constructor ---

    constructor() {
        owner = msg.sender;
    }

    // --- Functions ---

    function submitProof(
        bytes32 _lessonHash,
        uint8 _score,
        uint8 _level,
        bytes32 _sessionId
    ) external {
        require(_score >= 1 && _score <= 4, "Score must be 1-4");
        require(_level >= 1 && _level <= 4, "Level must be 1-4");

        ReviewProof memory proof = ReviewProof({
            lessonHash: _lessonHash,
            score: _score,
            level: _level,
            timestamp: block.timestamp,
            sessionId: _sessionId
        });

        proofs[msg.sender].push(proof);
        reviewCount[msg.sender] += 1;
        totalScore[msg.sender] += _score;

        emit ProofSubmitted(
            msg.sender,
            _lessonHash,
            _score,
            _level,
            block.timestamp,
            _sessionId
        );
    }

    function getProofCount(address _learner) external view returns (uint256) {
        return proofs[_learner].length;
    }

    function getProof(address _learner, uint256 _index) external view returns (ReviewProof memory) {
        require(_index < proofs[_learner].length, "Index out of bounds");
        return proofs[_learner][_index];
    }

    function getAverageScore(address _learner) external view returns (uint256) {
        uint256 count = reviewCount[_learner];
        if (count == 0) return 0;
        return totalScore[_learner] / count;
    }
}