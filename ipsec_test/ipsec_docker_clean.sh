#!/bin/bash
# ipsec_docker_cleanup.sh
# Automated teardown for the Docker-based IPsec lab.

# 1. Identify the project directory
LAB_DIR="${HOST_IPSEC_DIR:-/home/prash/veth-sswan-docker/ipsec_test/}"
cd "$LAB_DIR"
COMPOSE_FILE="$LAB_DIR/docker/docker-compose.yaml"

# 2. Check if the compose file exists before running
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "[-] Error: Compose file not found at $COMPOSE_FILE" >&2
    exit 1
fi

echo "[+] Cleaning up IPsec Docker Infrastructure..."

# 3. Execute Docker Compose Down
# This stops containers and removes networks created by 'up'
if docker compose -f "$COMPOSE_FILE" down; then
    echo "[+] Docker lab successfully torn down."
    exit 0
else
    echo "[-] Error: docker compose down failed." >&2
    exit 1
fi
