// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "forge-std/Script.sol";
import "../src/ProofOfKnowledge.sol";

contract DeployScript is Script {
    function run() external {
        vm.startBroadcast();
        ProofOfKnowledge pok = new ProofOfKnowledge();
        vm.stopBroadcast();

        console.log("ProofOfKnowledge deployed at:", address(pok));
    }
}