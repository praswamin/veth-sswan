#!/usr/bin/env python3
import socket
import struct
import time
import argparse
import random

def build_gtpu_packet(teid, payload_len=20):
    """
    Build a simple GTP-U header + dummy payload.
    Header fields: Version=1, PT=1, no extensions, Message Type=255 (dummy), Length, TEID
    """
    version_pt_flags = 0x30  # Version=1, PT=1, no next extension
    message_type = 0xff      # dummy type for testing
    length = payload_len + 4  # payload + TEID field (not including header)
    header = struct.pack("!BBH", version_pt_flags, message_type, length)
    teid_bytes = struct.pack("!I", teid)
    payload = bytes([random.randint(0, 255) for _ in range(payload_len)])
    return header + teid_bytes + payload

def send_gtpu_packets(src_ip, dst_ip, port=2152, teid=0x1234abcd, count=5, interval=1, iface=None):
    """
    Send GTP-U packets over UDP tunnel.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    if iface:
        sock.setsockopt(socket.SOL_SOCKET, 25, iface.encode())

    for i in range(count):
        packet = build_gtpu_packet(teid)
        sock.sendto(packet, (dst_ip, port))
        print(f"[{i+1}/{count}] Sent GTP-U packet TEID=0x{teid:x} {src_ip}->{dst_ip}:{port}")
        time.sleep(interval)

    sock.close()
    print(f"Completed sending {count} GTP-U packets.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send GTP-U UDP packets")
    parser.add_argument("--src-ip", required=True, help="Source IP address")
    parser.add_argument("--dst-ip", required=True, help="Destination IP address")
    parser.add_argument("--port", type=int, default=2152, help="UDP port (default 2152)")
    parser.add_argument("--teid", type=lambda x: int(x, 0), default=0x1234abcd, help="TEID value (hex or int)")
    parser.add_argument("--count", type=int, default=5, help="Number of packets to send")
    parser.add_argument("--interval", type=float, default=1.0, help="Interval between packets (seconds)")
    parser.add_argument("--iface", help="Bind to interface (optional)")
    args = parser.parse_args()

    send_gtpu_packets(
        src_ip=args.src_ip,
        dst_ip=args.dst_ip,
        port=args.port,
        teid=args.teid,
        count=args.count,
        interval=args.interval,
        iface=args.iface
    )

