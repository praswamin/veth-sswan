#!/bin/bash
set -e

echo "Cleaning up StrongSwan and namespaces..."

# List of namespaces used
NAMESPACES=(hostA hostB router)

# 1 Stop iperfn daemons (if running)
for ns in "${NAMESPACES[@]}"; do
    if ip netns list | grep -qw "$ns"; then
        echo "[+] Stopping charon in $ns..."
        ip netns exec $ns pkill iperf3 >/dev/null || true
    fi
done

# 2 Stop charon daemons (if running)
for ns in "${NAMESPACES[@]}"; do
    if ip netns list | grep -qw "$ns"; then
        echo "[+] Stopping charon in $ns..."
        ip netns exec $ns pkill charon 2>/dev/null || true
    fi
done

# 3 Unmount namespace /etc binds
for ns in hostA hostB; do
    if mount | grep -q "/etc/ipsec-ns/$ns on /etc"; then
        echo "[+] Unmounting /etc bind in $ns..."
        ip netns exec $ns umount /etc || true
    fi
done

# 4 Flush StrongSwan and XFRM states
for ns in hostA hostB; do
    if ip netns list | grep -qw "$ns"; then
        echo "[+] Flushing IPsec (XFRM) state in $ns..."
        ip netns exec $ns ip xfrm state flush 2>/dev/null || true
        ip netns exec $ns ip xfrm policy flush 2>/dev/null || true
    fi
done

# 5 Delete veths and namespaces
for ns in "${NAMESPACES[@]}"; do
    echo "[+] Deleting namespace $ns..."
    ip netns del $ns 2>/dev/null || true
done

# 6 Remove config directories
echo "[+] Cleaning config, log directories..."
rm -rf /etc/ipsec-ns
rm -f /var/log/charon-hostA.log /var/log/charon-hostB.log

# 7 Check for leftover veths
echo "[+] Removing leftover veth interfaces..."
for veth in vethA-hostA vethA-router vethB-hostB vethB-router; do
    ip link del $veth 2>/dev/null || true
done

echo "Cleanup complete!"

