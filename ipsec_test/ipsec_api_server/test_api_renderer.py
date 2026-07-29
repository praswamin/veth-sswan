from jinja2 import Environment, FileSystemLoader
import requests
import json
import os

# Global Configuration
#HOST_PATH = os.environ.get('HOST_IPSEC_DIR', '/home/prash/veth-sswan-docker/ipsec_test/')
HOST_PATH = os.environ.get('HOST_IPSEC_DIR', '')

# test_api_renderer.py
from jinja2 import Environment, FileSystemLoader
import os

def render_swanctl(params, template_name='swanctl.conf.j2'):
    """
    Renders the swanctl.conf and prints the result for manual verification.
    """
    #base_path = os.environ.get('HOST_IPSEC_DIR', '/home/prash/veth-sswan/ipsec_test/')
    base_path = os.environ.get('HOST_IPSEC_DIR', '')
    template_dir = os.path.join(base_path, 'templates')
    
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(template_name)
    
    rendered_config = template.render(**params)

    # Print to the API Server console for manual inspection
    print("\n" + "="*30)
    print("--- PRE-APPLICATION CONFIGURATION CHECK ---")
    print(rendered_config)
    print("="*30 + "\n")

    return rendered_config
'''
# 1. Setup Jinja2 Environment (Match your mcp_server.py path)
env = Environment(loader=FileSystemLoader('/home/prash/mcp-veth-sswan/ipsec_test/templates'))
template = env.get_template('swanctl.conf.j2')

# 2. Define Test Data (Simulating session state)
# This includes the original tunnel and one new dynamic tunnel
test_children = [
    {"name": "net", "local_ts": "10.10.0.1/28", "remote_ts": "10.10.1.1/28"},
    {"name": "net2", "local_ts": "10.10.0.2/32", "remote_ts": "10.10.1.2/32"}
]

render_vars = {
    "connection_name": "net-test",
    "local_ip": "10.200.1.10",
    "remote_ip": "10.200.2.20",
    "local_id": "hostA",
    "remote_id": "hostB",
    "children": test_children
}

# 3. Render and Print (Check for syntax/braces errors)
rendered_config = template.render(**render_vars)
print("--- RENDERED CONFIGURATION ---")
print(rendered_config)
print("------------------------------")

# 4. Push to API Server
API_URL = "http://localhost:8080/config/update_swanctl"
payload = {"host": "hostA", "config": rendered_config}

try:
    response = requests.post(API_URL, json=payload)
    print(f"API Response Status: {response.status_code}")
    print(f"API Response Body: {response.text}")
except Exception as e:
    print(f"Failed to connect to api_server.py: {e}")

'''