from mcp.server.fastmcp import FastMCP
import requests
from jinja2 import Environment, FileSystemLoader

# Initialize Jinja2 environment
env = Environment(loader=FileSystemLoader('/path/to/veth-sswan//ipsec_test/templates'))
template = env.get_template('swanctl.conf.j2')

# In-memory state to track children for this session
session_children = {
    "hostA": [{"name": "net", "local_ts": "10.10.0.1/28", "remote_ts": "10.10.1.1/28"}],
    "hostB": [{"name": "net", "local_ts": "10.10.1.1/28", "remote_ts": "10.10.0.1/28"}]
}

# Initialize the MCP server
mcp = FastMCP("Veth-SSwan-Orchestrator")

# Base URL for the existing ipsec_api_server
API_URL = "http://localhost:8080"

@mcp.tool()
def setup_infrastructure() -> str:
    """Run the initial provisioning for veth-pairs and namespaces."""
    # This wraps the /api/ipsec/setup endpoint
    response = requests.post(f"{API_URL}/api/ipsec/setup")
    return response.text

@mcp.tool()
def initialize_host(ns: str) -> str:
    """Initialize a specific namespace (e.g., 'hostA') environment."""
    # Wraps /api/ipsec/init_host
    response = requests.post(f"{API_URL}/api/ipsec/init_host", json={"ns": ns})
    return response.text

@mcp.tool()
def load_vpn_config(ns: str) -> str:
    """Load strongSwan configurations for a specific namespace."""
    # Wraps /api/ipsec/load
    response = requests.post(f"{API_URL}/api/ipsec/load", json={"ns": ns})
    return response.text

@mcp.tool()
def get_tunnel_stats(ns: str) -> str:
    """Get real-time IPsec SA statistics for a namespace."""
    # Wraps /api/ipsec/stats (GET method)
    params = {"ns": ns, "format": "table"}
    response = requests.get(f"{API_URL}/api/ipsec/stats", params=params)
    return response.text

@mcp.tool()
def initiate_tunnel(ns: str, ike: str, child: str) -> str:
    """Initiate an IPsec tunnel by establishing a child security association.
    
    Args:
        ns: Namespace (e.g., 'hostA' or 'hostB')
        ike: IKE connection name
        child: Child SA name
    
    Returns:
        Status and output from swanctl initiate command
    """
    # Wraps /api/ipsec/child/add
    payload = {"ns": ns, "ike": ike, "child": child}
    response = requests.post(f"{API_URL}/api/ipsec/child/add", json=payload)
    return response.text

@mcp.tool()
def add_host_ip(host_name: str, ip_address: str) -> str:
    """
    Adds a new IP address to the loopback interface of a specific host namespace.
    This is required before adding new Child SA entries for that IP.
    :param host_name: The namespace name ('hostA' or 'hostB').
    :param ip_address: The IP address with CIDR (e.g., '10.10.0.5/32').
    """
    payload = {"ns": host_name, "ip": ip_address}
    
    try:
        response = requests.post(f"{API_URL}/namespace/add_ip", json=payload)
        if response.status_code == 200:
            return f"Successfully provisioned {ip_address} in {host_name} namespace."
        else:
            error_detail = response.json().get('error', 'Unknown error')
            return f"Failed to add IP: {error_detail}"
    except Exception as e:
        return f"Communication error with Worker: {str(e)}"




@mcp.tool()
def add_child_sa(host_name: str, child_name: str, local_ts: str, remote_ts: str) -> str:
    """
    Dynamically adds a new Child SA to the swanctl configuration.
    :param host_name: The host to update ('hostA' or 'hostB').
    :param child_name: Name for the new tunnel entry.
    :param local_ts: Local Traffic Selector (IP/CIDR).
    :param remote_ts: Remote Traffic Selector (IP/CIDR).
    """
    # 1. Update session state
    new_child = {"name": child_name, "local_ts": local_ts, "remote_ts": remote_ts}
    session_children[host_name].append(new_child)

    # 2. Define rendering variables based on host
    is_host_a = (host_name == "hostA")
    render_vars = {
        "connection_name": "net-test",
        "local_ip": "10.200.1.10" if is_host_a else "10.200.2.20",
        "remote_ip": "10.200.2.20" if is_host_a else "10.200.1.10",
        "local_id": "hostA" if is_host_a else "hostB",
        "remote_id": "hostB" if is_host_a else "hostA",
        "children": session_children[host_name]
    }

    # 3. Render the config
    config_text = template.render(**render_vars)

    # 4. Send to Worker (api_server.py) to apply
    payload = {"host": host_name, "config": config_text}
    response = requests.post(f"{API_URL}/config/update_swanctl", json=payload)
    
    if response.status_code == 200:
        return f"Successfully added {child_name} to {host_name} and reloaded swanctl."
    return f"Error updating config: {response.text}"


@mcp.tool()
def cleanup_infrastructure() -> str:
    """Clean up all infrastructure and remove namespaces, veth pairs, and IPsec sessions."""
    # Wraps /api/ipsec/cleanup
    response = requests.post(f"{API_URL}/api/ipsec/cleanup")
    return response.text

@mcp.prompt()
def troubleshoot_tunnel(host_name: str):
    """
    Standardizes the troubleshooting flow for a specific namespace.
    """
    return f"Check the status of the IPsec tunnel in namespace {host_name}. " \
           f"Provide the SPI values, check if the loopback IPs are reachable, " \
           f"and summarize any errors found in /var/log/charon-{host_name}.log."

if __name__ == "__main__":
    mcp.run()
