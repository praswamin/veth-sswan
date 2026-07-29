# Use a lean base
FROM debian:bookworm-slim

# Install strongSwan and networking utilities
RUN apt-get update && apt-get install -y \
    strongswan \
    strongswan-swanctl \
    charon-systemd \
    libcharon-extra-plugins \
    libcharon-extauth-plugins \
    iproute2 \
    iperf3 \
    iputils-ping \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Expose the VICI socket path for the MCP server to connect
VOLUME /etc/swanctl
VOLUME /var/log

# Start the charon-systemd daemon in the foreground
# This keying daemon manages IKE sessions and SA negotiation
CMD ["/usr/sbin/charon-systemd"]
