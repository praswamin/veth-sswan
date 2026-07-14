# veth-sswan
Project integrating veth-pair and strongSwan on a Raspberry Pi system

The Project would explore setting up veth-pairs paired with strongSwan configuration enabling IPsec tunnels between them.

* Architecture
The lab simulates a point-to-point network topology across isolated environments:
Namespaces: hostA, router, and hostB provide process and network isolation

** Connectivity: veth-pairs act as virtual cables connecting the namespaces

** Security: strongSwan (charon-systemd) manages IPsec tunnels between loopback interfaces

** Orchestration: It utilizes the Model Context Protocol (MCP) to provide an AI-native orchestration layer, allowing assistants like GitHub Copilot to manage the entire lab lifecycle through natural language
 A FastMCP server translates AI intent into ip netns exec and swanctl commands


The Topology used for the setup:


<img width="587" height="269" alt="Topology" src="https://github.com/user-attachments/assets/51bbf0e7-5a66-4ee8-8af3-b5e264eaf6a0" />


'''
* Directory Structure
veth-sswan/
├── lab_setup/                  	# Manual environment scripts
│   └── ipsec_ns_setup.sh       	# Script for manual namespace creation
├── configs/                    	# strongSwan configuration templates
│   ├── hostA/                  	# hostA namespace configs
│   └── hostB/                  	# hostB namespace configs
├── veth-sswan-orchestrator/      # MCP Orchestration layer
│   ├── src/
│   │   └── mcp_api_server.py   	# FastMCP server implementation
│   ├── requirements.txt        	# Python dependencies (mcp, etc.)
│   └── README.md               	# Orchestrator documentation
├── tests/                      	# Pytest verification suite
├── .vscode/
│   └── mcp.json                	# VS Code MCP server registration
├── templates/
│   └── swanctl.conf.j2          # Jinja2 template to update swanctl configuration
├── ipsec_api_server/
│   └── api_server.py            # Backend orchestrator (runs with sudo)
│   └── test_api_lib				         # API library with help functions
│   └── test_api_renderer			     # Library to render swanctl config from Jinja2 templates
└── README.md                   	# Main project documentation
'''

```
