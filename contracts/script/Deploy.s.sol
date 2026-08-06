// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import {Script, console} from "forge-std/Script.sol";
import {ProofOfKnowledge} from "../src/ProofOfKnowledge.sol";

/// @notice Deploys ProofOfKnowledge with the agent's signing address
/// authorised as the first attestor.
/// @dev Set ATTESTOR_ADDRESS to the address derived from the key the agent
/// signs attestations with. It defaults to the broadcaster, which is only
/// right when the deployer and the agent share a key.
contract DeployScript is Script {
    function run() external returns (ProofOfKnowledge) {
        address attestor = vm.envOr("ATTESTOR_ADDRESS", msg.sender);

        vm.startBroadcast();
        ProofOfKnowledge pok = new ProofOfKnowledge(attestor);
        vm.stopBroadcast();

        console.log("ProofOfKnowledge deployed at:", address(pok));
        console.log("Initial attestor:           ", attestor);
        console.log("Owner:                      ", pok.owner());

        return pok;
    }
}
