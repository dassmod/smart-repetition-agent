"""
Blockchain bridge - submits review proofs to Ethereum Sepolia.

The agent signs EIP-712 attestations naming the learner, rather than calling
the contract as itself. See contracts/src/ProofOfKnowledge.sol for why: signing
as the caller collapsed every learner onto this one relayer address.
"""

import os
import json
from web3 import Web3
from eth_account.messages import encode_typed_data
from dotenv import load_dotenv


load_dotenv()


def learner_address(user_id: str) -> str:
    """
    Derive a stable pseudonymous on-chain identifier for a learner.

    Telegram users hold no keys, so there is no wallet to credit. We hash the
    user id down to an address instead. It is an identifier, not an account:
    nobody holds its private key, and it can neither sign nor spend. What it
    buys is that one learner's history stays separate from another's on-chain.

    Linking a real wallet a learner controls would be strictly better, and is
    the natural next step for this contract.
    """
    digest = Web3.keccak(text=f"proof-of-knowledge:learner:{user_id}")
    return Web3.to_checksum_address(digest[-20:])


class BlockchainBridge:
    """Connects to Sepolia and interacts with the ProofOfKnowledge contract."""

    def __init__(self):
        rpc_url = os.environ.get("SEPOLIA_RPC_URL")
        private_key = os.environ.get("SEPOLIA_PRIVATE_KEY")
        contract_address = os.environ.get("POK_CONTRACT_ADDRESS")

        if not all([rpc_url, private_key, contract_address]):
            raise ValueError(
                "Missing blockchain environment variables. "
                "Set SEPOLIA_RPC_URL, SEPOLIA_PRIVATE_KEY, POK_CONTRACT_ADDRESS in .env"
            )

        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        self.private_key = private_key
        self.account = self.w3.eth.account.from_key(private_key)
        self.address = self.account.address

        # Load ABI from compiled contract
        abi_path = os.path.join(
            os.path.dirname(__file__), "..",
            "contracts", "out", "ProofOfKnowledge.sol", "ProofOfKnowledge.json"
        )
        with open(abi_path, 'r') as f:
            contract_json = json.load(f)

        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=contract_json['abi']
        )

        # An exported POK_CONTRACT_ADDRESS beats .env, because load_dotenv does
        # not override the real environment. Pointing at a stale deployment is
        # therefore easy and otherwise silent, so fail here rather than at the
        # first reverted submission.
        if not self._contract_is_current():
            raise ValueError(
                f"POK_CONTRACT_ADDRESS={self.contract.address} is not a "
                "current ProofOfKnowledge deployment: it has no "
                "domainSeparator(), so it predates EIP-712 attestations. "
                "If you exported this variable into your shell, that value "
                "overrides .env; unset it or start a new shell."
            )

    def _contract_is_current(self) -> bool:
        """Cheap probe for a function only the current contract exposes."""
        try:
            self.contract.functions.domainSeparator().call()
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------- signing

    def _sign_attestation(
        self, learner: str, lesson_hash: bytes, score: int, level: int, session_hash: bytes
    ) -> bytes:
        """Sign the EIP-712 ReviewProof struct the contract expects."""
        typed_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "ReviewProof": [
                    {"name": "learner", "type": "address"},
                    {"name": "lessonHash", "type": "bytes32"},
                    {"name": "score", "type": "uint8"},
                    {"name": "level", "type": "uint8"},
                    {"name": "sessionId", "type": "bytes32"},
                ],
            },
            "primaryType": "ReviewProof",
            "domain": {
                "name": "ProofOfKnowledge",
                "version": "1",
                "chainId": self.w3.eth.chain_id,
                "verifyingContract": self.contract.address,
            },
            "message": {
                "learner": learner,
                "lessonHash": lesson_hash,
                "score": score,
                "level": level,
                "sessionId": session_hash,
            },
        }
        signable = encode_typed_data(full_message=typed_data)
        signed = self.account.sign_message(signable)
        return signed.signature

    # ------------------------------------------------------------ submission

    def submit_proof(
        self, learner: str, lesson_id: str, score: int, level: int, session_id: str
    ) -> str:
        """
        Record one review proof for `learner`.

        The attestation is signed with the agent's key; this wallet relays it
        and pays the gas. Tampering with any field on the way invalidates the
        signature, so the relayer is untrusted by construction.
        """
        learner = Web3.to_checksum_address(learner)
        lesson_hash = Web3.keccak(text=lesson_id)
        session_hash = Web3.keccak(text=session_id)

        signature = self._sign_attestation(
            learner, lesson_hash, score, level, session_hash
        )

        call = self.contract.functions.submitProof(
            learner, lesson_hash, score, level, session_hash, signature
        )

        tx = call.build_transaction({
            'from': self.address,
            'nonce': self.w3.eth.get_transaction_count(self.address),
            'gas': self._estimate_gas(call),
            'gasPrice': self.w3.eth.gas_price,
        })

        signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hex = tx_hash.hex()
        url = f"https://sepolia.etherscan.io/tx/{tx_hex}"

        # A mined transaction is not a successful one. Without this check a
        # revert still returns a hash and reads as success, which is how a
        # wrong contract address or an unauthorised attestor stays invisible.
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        if receipt["status"] != 1:
            raise RuntimeError(
                f"Proof submission reverted on-chain: {url}\n"
                f"  contract: {self.contract.address}\n"
                f"  relayer:  {self.address}\n"
                f"  learner:  {learner}\n"
                "Common causes: POK_CONTRACT_ADDRESS points at an older "
                "deployment, the signer is not an authorised attestor, or this "
                "session id was already used."
            )

        print(f"Proof submitted: {url}")

        return tx_hex

    def submit_session_proofs(
        self,
        session_results: list[dict],
        session_questions: list[str],
        user_id: str = "local",
    ) -> list[str]:
        """
        Submit proofs for an entire review session.

        Args:
            session_results: Dicts with 'lesson_id', 'score', 'level'
            session_questions: Question strings asked during the session
            user_id: Identifier for the learner, e.g. a Telegram user id

        Returns:
            List of transaction hashes
        """
        questions_text = "|".join(session_questions)
        session_root = Web3.keccak(text=questions_text).hex()
        learner = learner_address(user_id)

        tx_hashes = []
        for index, result in enumerate(session_results):
            # The contract consumes each session id exactly once, so every
            # proof in a session needs its own. Reusing one id across a session
            # would let only the first proof land and revert the rest.
            proof_session_id = f"{session_root}:{index}:{result['lesson_id']}"
            try:
                tx_hash = self.submit_proof(
                    learner=learner,
                    lesson_id=result['lesson_id'],
                    score=result['score'],
                    level=result['level'],
                    session_id=proof_session_id,
                )
                tx_hashes.append(tx_hash)
            except Exception as e:
                print(f"  Failed to submit proof for {result['lesson_id']}: {e}")

        return tx_hashes

    # ----------------------------------------------------------------- reads

    def get_proof_count(self, user_id: str = "local") -> int:
        """Number of proofs recorded for a learner."""
        return self.contract.functions.getProofCount(learner_address(user_id)).call()

    def get_average_score(self, user_id: str = "local") -> float:
        """
        Mean score for a learner.

        The contract returns the average scaled by 1e18, because integer
        division would otherwise report a 3.75 average as 3.
        """
        scaled = self.contract.functions.getAverageScore(
            learner_address(user_id)
        ).call()
        return scaled / 1e18

    def is_connected(self) -> bool:
        """Check if connected to the network."""
        return self.w3.is_connected()

    def _estimate_gas(self, call) -> int:
        """Estimate gas for a prepared call, with fallback."""
        try:
            estimated = call.estimate_gas({'from': self.address})
            return int(estimated * 1.2)  # 20% buffer
        except Exception:
            return 300000  # Safe fallback
