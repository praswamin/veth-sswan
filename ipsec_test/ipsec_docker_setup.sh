#!/bin/bash
# ipsec_docker_setup.sh
# Standard automated setup for the Docker-based IPsec lab architecture .

# 1. Identify the project directory
# Utilizes the HOST_IPSEC_DIR variable passed from api_server.py.
export HOST_IPSEC_DIR="${HOST_IPSEC_DIR:-/home/prash/veth-sswan-docker/ipsec_test}"

#BASE_DIR="${HOST_IPSEC_DIR:-/home/prash/veth-sswan-docker/ipsec_test}"
LAB_DIR="${HOST_IPSEC_DIR}/docker/"

# line 9: Now cd will point to the correct absolute path even if the env is empty
cd "$LAB_DIR" || { echo "[-] Error: Could not enter $LAB_DIR"; exit 1; }

echo "[+] Initializing IPsec Docker Infrastructure..."

# 2. Execute Docker Compose
# -d: Detached mode allows the API server to remain responsive.
# --build: Ensures any local configuration changes (swanctl.conf) are incorporated.
if docker compose up -d --build; then
    echo "[+] Docker compose command executed successfully."
else
    echo "[-] Error: docker compose failed to build or start containers." >&2
    exit 1
fi

# 3. Verify Container Runtime Status
# Validates that the core topology nodes are active.
EXPECTED_NODES=("hostA" "router" "hostB")
ALL_RUNNING=true
SETUP_VALID=true

for node in "${EXPECTED_NODES[@]}"; do
    # Use docker inspect to check for the 'running' state
    STATUS=$(docker inspect -f '{{.State.Status}}' "$node" 2>/dev/null || echo "not_found")
    
    if [ "$STATUS" == "running" ]; then
        echo "[+] Node '$node' is confirmed running."
    else
        echo "[-] Error: Node '$node' is not running (Current state: $STATUS)." >&2
        ALL_RUNNING=false
    fi
done

# 4. Base Connectivity Check (Mirrors ipsec_ns_setup.sh logic) [2]
# Pings hostB (10.200.2.20) from hostA to confirm the routing through the 'router' container.
if [ "$ALL_RUNNING" = true ]; then
    echo "[+] Testing base connectivity between nodes..."
    # -c 2: send 2 packets; > /dev/null: suppress output unless there is an error
    if docker exec hostA ping -c 4 10.200.2.20 > /dev/null 2>&1; then
        echo "[+] Connectivity confirmed: hostA can reach hostB (10.200.2.20)."
    else
        echo "[-] Error: Basic ping failed between hostA and hostB. Check Docker networking." >&2
        SETUP_VALID=false
    fi
fi

# 5. Standardized Return for the Python Driver 
if [ "$SETUP_VALID" = true ]; then
    echo "[+] IPsec Lab successfully initialized in DOCKER mode."
    exit 0
else
    echo "[-] Infrastructure validation failed." >&2
    exit 1
fi
