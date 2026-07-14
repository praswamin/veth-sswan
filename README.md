# veth-sswan
Project integrating veth-pair and strongSwan on a Raspberry Pi system

The Project would explore setting up veth-pairs paired with strongSwan configuration enabling IPsec tunnels between them.
Architecture
The lab simulates a point-to-point network topology across isolated environments:
Namespaces: hostA, router, and hostB provide process and network isolation
.
Connectivity: veth-pairs act as virtual cables connecting the namespaces
.
Security: strongSwan (charon-systemd) manages IPsec tunnels between loopback interfaces
. It utilizes the Model Context Protocol (MCP) to provide an AI-native orchestration layer, allowing assistants like GitHub Copilot to manage the entire lab lifecycle through natural language
Orchestration: A FastMCP server translates AI intent into ip netns exec and swanctl commands


The Topology used for the setup:


<img width="587" height="269" alt="Topology" src="https://github.com/user-attachments/assets/51bbf0e7-5a66-4ee8-8af3-b5e264eaf6a0" />

