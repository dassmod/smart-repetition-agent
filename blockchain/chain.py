"""
Blockchain bridge - submits review proofs to Ethereum Sepolia.
"""

import os
import json
from web3 import Web3
from dotenv import load_dotenv
import time


load_dotenv()


class BlockchainBridge:
    """Connects to Sepolia and interacts with ProofOfKnowledge contract."""

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
            address=contract_address,
            abi=contract_json['abi']
        )

    def submit_proof(self, lesson_id: str, score: int, level: int, session_id: str) -> str:
        lesson_hash = Web3.keccak(text=lesson_id)
        session_hash = Web3.keccak(text=session_id)

        tx = self.contract.functions.submitProof(
            lesson_hash, score, level, session_hash
        ).build_transaction({
            'from': self.address,
            'nonce': self.w3.eth.get_transaction_count(self.address),
            'gas': self._estimate_gas(lesson_hash, score, level, session_hash),
            'gasPrice': self.w3.eth.gas_price,
        })

        signed = self.w3.eth.account.sign_transaction(tx, self.private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hex = tx_hash.hex()

        # Wait for transaction to be mined before returning
        try:
            self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        except Exception:
            # Transaction may still go through, continue anyway
            pass

        print(f"  Proof submitted: https://sepolia.etherscan.io/tx/{tx_hex}")

        return tx_hex

    def submit_session_proofs(self, session_results: list[dict], session_questions: list[str]) -> list[str]:
        """
        Submit proofs for an entire review session.

        Args:
            session_results: List of dicts with 'lesson_id', 'score', 'level'
            session_questions: List of question strings asked during session

        Returns:
            List of transaction hashes
        """
        # Hash all questions into one session ID
        questions_text = "|".join(session_questions)
        session_id = Web3.keccak(text=questions_text).hex()

        tx_hashes = []
        for result in session_results:
            try:
                tx_hash = self.submit_proof(
                    lesson_id=result['lesson_id'],
                    score=result['score'],
                    level=result['level'],
                    session_id=session_id
                )
                tx_hashes.append(tx_hash)
            except Exception as e:
                print(f"  Failed to submit proof for {result['lesson_id']}: {e}")

        return tx_hashes

    def get_proof_count(self) -> int:
        """Get total number of proofs submitted by this wallet."""
        return self.contract.functions.getProofCount(self.address).call()

    def get_average_score(self) -> int:
        """Get average score across all proofs."""
        return self.contract.functions.getAverageScore(self.address).call()

    def is_connected(self) -> bool:
        """Check if connected to the network."""
        return self.w3.is_connected()

    def _estimate_gas(self, lesson_hash, score, level, session_hash) -> int:
        """Estimate gas for submitProof, with fallback."""
        try:
            estimated = self.contract.functions.submitProof(
                lesson_hash, score, level, session_hash
            ).estimate_gas({'from': self.address})
            return int(estimated * 1.2)  # 20% buffer
        except Exception:
            return 200000  # Safe fallback