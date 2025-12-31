#!/bin/bash
set -e

# === Cleanup any old setup ===
for ns in hostA router hostB; do
  ip netns del $ns 2>/dev/null || true
done
rm -rf /etc/ipsec-ns
mkdir -p /etc/ipsec-ns

echo "[+] Creating network namespaces..."
ip netns add hostA
ip netns add router
ip netns add hostB

echo "[+] Creating veth pairs..."
ip link add vethA-hostA type veth peer name vethA-router
ip link add vethB-hostB type veth peer name vethB-router

# Attach interfaces
ip link set vethA-hostA netns hostA
ip link set vethA-router netns router
ip link set vethB-hostB netns hostB
ip link set vethB-router netns router

echo "[+] Assigning IP addresses..."
ip -n hostA addr add 10.200.1.10/24 dev vethA-hostA
ip -n router addr add 10.200.1.1/24 dev vethA-router
ip -n router addr add 10.200.2.1/24 dev vethB-router
ip -n hostB addr add 10.200.2.20/24 dev vethB-hostB
ip -n hostA addr add 10.10.0.1/32 dev lo
ip -n hostB addr add 10.10.1.1/32 dev lo

# Bring all interfaces up
for ns in hostA router hostB; do
  ip -n $ns link set lo up
done
ip -n hostA link set vethA-hostA up
ip -n hostA link set lo up
ip -n router link set vethA-router up
ip -n router link set vethB-router up
ip -n hostB link set vethB-hostB up
ip -n hostB link set lo up

echo "[+] Setting routes..."
ip -n hostA route add default via 10.200.1.1
ip -n hostB route add default via 10.200.2.1

# Enable forwarding in router
ip netns exec router sysctl -w net.ipv4.ip_forward=1 >/dev/null
ip netns exec hostA sysctl -w net.ipv4.ip_forward=1
ip netns exec hostB sysctl -w net.ipv4.ip_forward=1

echo "[+] Testing base connectivity..."
ip netns exec hostA ping -c 2 10.200.2.20 || echo " Basic ping failed, check veth setup"

 #=== Create StrongSwan configs ===
echo "[+] Setting up StrongSwan namespace configs..."
mkdir -p /etc/ipsec-ns/hostA/{swanctl,d}
mkdir -p /etc/ipsec-ns/hostB/{swanctl,d}

echo "[+] Setting up StrongSwan configs..."
cat >/etc/ipsec-ns/hostA/strongswan.conf <<'EOF'
charon {
    #basic logging setup
    filelog {
        my_log_file {
            path = /var/log/charon-hostA.log
            time_format = %b %e %T
            append = yes
            default = 1
            flush_line = yes
        }
    }

    #load all default plugins
    plugins {
        vici {
            socket = unix:///etc/ipsec.d/run/charon-hostA.vici
        }
        #include strongswan.d/charon/*.conf
    }
}
EOF

 #--- hostA config ---
cat >/etc/ipsec-ns/hostA/swanctl/swanctl.conf <<'EOF'
connections {
    net-test {
        local_addrs  = 10.200.1.10
        remote_addrs = 10.200.2.20

        local {
            auth = psk
            id = hostA
        }
        remote {
            auth = psk
            id = hostB
        }

        children {
            net {
                local_ts  = 10.10.0.1/28
                remote_ts = 10.10.1.1/28
                esp_proposals = aes128-sha256
            }
        }

        version = 2
        proposals = aes128-sha256-modp2048
    }
}

secrets {
    ike-hostA-hostB {
        id-1 = hostA
        id-2 = hostB
        secret = "strongsecret"
    }
}
EOF

 #--- hostB config ---
echo "[+] Setting up StrongSwan configs..."
cat >/etc/ipsec-ns/hostB/strongswan.conf <<'EOF'
charon {
    #basic logging setup
    filelog {
        my_log_file {
            path = /var/log/charon-hostB.log
            time_format = %b %e %T
            append = yes
            default = 1
            flush_line = yes
        }
    }

    #load all default plugins
    plugins {
        vici {
            socket = unix:///etc/ipsec.d/run/charon-hostB.vici
        }
        #include strongswan.d/charon/*.conf
    }
}
EOF

cat >/etc/ipsec-ns/hostB/swanctl/swanctl.conf <<'EOF'
connections {
    net-test {
        local_addrs  = 10.200.2.20
        remote_addrs = 10.200.1.10

        local {
            auth = psk
            id = hostB
        }
        remote {
            auth = psk
            id = hostA
        }

        children {
            net {
                local_ts  = 10.10.1.1/28
                remote_ts = 10.10.0.1/28
                esp_proposals = aes128-sha256
            }
        }

        version = 2
        proposals = aes128-sha256-modp2048
    }
}

secrets {
    ike-hostA-hostB {
        id-1 = hostB
        id-2 = hostA
        secret = "strongsecret"
    }
}
EOF

#
echo "Setup complete!"

