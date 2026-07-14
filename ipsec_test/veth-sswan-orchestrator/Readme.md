Installation & Backend Setup
1. **Install Dependencies**

1.1: Navigate to the orchestrator directory and install the required Python packages:
cd veth-sswan-orchestrator
uv: Recommended for fast, reliable dependency management
uv pip install -r requirements.txt
The requirements.txt includes the mcp SDK for protocol communication.

*Verify Installation*: Ensure the mcp library is available within your environment

1.2: **Configuring Sudo**
Configuring Sudo for the MCP Server

To allow the AI assistant to manage network namespaces and tunnels non-interactively, the user running the MCP server must have passwordless sudo access for networking commands.
Edit the Sudoers File
  Run the following command to open the sudoers configuration:
  
  sudo visudo
  
Add the Entry
  Add the following line at the end of the file, replacing <YOUR_USERNAME> with your actual Linux username:
  <YOUR_USERNAME> ALL=(ALL) NOPASSWD: /usr/sbin/ip, /usr/sbin/swanctl, /usr/sbin/charon-systemd, /usr/bin/python3 /path/to/veth-sswan/api_server.py

2. **Start the Orchestrator API**
Run the backend API server with root privileges to allow it to execute namespace commands:
sudo python3 /path/to/veth-sswan/ipsec_api_server/api_server.py
Note: This server must be active for the MCP tools to function.

3. **Register with VS Code**
Create or update your .vscode/mcp.json file to include the orchestrator:

{
  "mcpServers": {
    "veth-sswan-orchestrator": {
      "command": "python3",
      "args": ["/path/to/veth-sswan/veth-sswan-orchestrator/src/server.py"]
    }
  }
}

Restart VS Code or use "Developer: Reload Window" to discover the tools

**Usage (AI Orchestration)**
Once the backend is running and registered, you can manage the entire lab lifecycle using GitHub Copilot Chat.

1. **Lab Initialization**
Ask Copilot to prepare the virtual networking environment:
"Setup the lab infrastructure." (Triggers the initialization of namespaces and veth pairs)

"Initialize the hosts and start the networking daemons." (Assigns IPs, brings interfaces up, and starts charon-systemd)

2. **Tunnel Management**
Instruct the AI to configure and establish the secure path:

"Load the IPsec connections on both hostA and hostB." (Uses swanctl --load-all)

"Establish the IPsec tunnel between hostA and hostB." (Uses swanctl --initiate)

3. **Monitoring and Testing**
Use natural language to verify the state of your network:
"Show me the status of the Security Associations on hostA." (Uses swanctl --list-sas)

"Run a ping test between the loopback interfaces to verify encryption."

***Troubleshooting***
VICI Socket: If commands fail, verify the socket path in strongswan.conf matches the path the orchestrator expects (e.g., charon-hostA.vici)

***Permissions***: The api_server.py must run with sudo to manage Linux network namespaces

Trust: When prompted by VS Code, ensure you select "Trust" for the MCP server to allow tool execution