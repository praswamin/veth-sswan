#!/usr/bin/env python3
import socket
import struct
import random
import time
import argparse
import signal
import sys
import os
import json

# GTP-U constants
GTPU_PORT = 2152
GTPU_VERSION = 1
GTPU_PT = 1
GTPU_HEADER_FLAGS = (GTPU_VERSION << 5) | GTPU_PT
GTPU_MSGTYPE_GTPU = 0xFF

running = True

def signal_handler(sig, frame):
    """Handle Ctrl+C for clean exit"""
    global running
    print("\n[INFO] Stopping GTP-U packet sender...")
    running = False

signal.signal(signal.SIGINT, signal_handler)

#def build_gtpu_packet(teid, payload):
#    """Build a GTP-U packet with header + payload"""
#    total_length = len(payload)
#    header = struct.pack("!BBH", GTPU_HEADER_FLAGS, GTPU_MSGTYPE_GTPU, total_length)
#    header += struct.pack("!I", teid)
#    return header + payload

def build_gtpu_packet(local_teid, remote_teid, payload, direction="uplink"):
    """
    Build a GTP-U packet with both local and remote TEIDs.
    
    Args:
        local_teid (int): TEID used for local (sending) side.
        remote_teid (int): TEID expected by the remote (receiving) side.
        payload (bytes): GTP-U user payload.
        direction (str): 'uplink' or 'downlink'. Determines which TEID to use.
    
    Returns:
        bytes: Complete GTP-U packet (header + payload)
    """
    # Standard GTP-U header fields
    version = 1       # Version 1
    protocol_type = 1 # GTP (not GTP')
    reserved = 0
    message_type = 0xFF  # G-PDU (data packet)
    
    # Use TEID according to direction
    if direction == "uplink":
        #teid = local_teid
        teid = remote_teid
    else:
        #teid = remote_teid
        teid = local_teid

    # Build header flags (8 bits)
    flags = (version << 5) | (protocol_type << 4) | reserved

    # Payload length
    length = len(payload)

    # Pack header (8 bytes): Flags(1) | MessageType(1) | Length(2) | TEID(4)
    header = struct.pack("!BBH I", flags, message_type, length, teid)

    # Combine header and payload
    return header + payload

#def load_teids_from_file(filename):
#    """Load TEID pairs (local, remote) from a file"""
#    teid_pairs = []
#    with open(filename, "r") as f:
#        for line in f:
#            line = line.strip().replace(",", " ")
#            if not line or line.startswith("#"):
#                continue
#            parts = line.split()
#            if len(parts) >= 2:
#                local_teid = int(parts[0])
#                remote_teid = int(parts[1])
#                teid_pairs.append((local_teid, remote_teid))
#            if len(teid_pairs) >= 10:
#                break
#    return teid_pairs

def load_teids_from_file(teid_file):
    """
    Load TEID pairs (local/remote) from a JSON file.
    
    Expected JSON format:
    [
        {"local_teid": 1001, "remote_teid": 2001},
        {"local_teid": 1002, "remote_teid": 2002}
    ]
    """
    if not os.path.exists(teid_file):
        raise FileNotFoundError(f"TEID file not found: {teid_file}")
    
    try:
        with open(teid_file, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in TEID file: {e}")
    
    if not isinstance(data, list):
        raise ValueError("TEID file must contain a list of TEID pair objects")

    teid_list = []
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("Each TEID entry must be a JSON object")
        if "local_teid" not in entry or "remote_teid" not in entry:
            raise ValueError("Each TEID entry must include 'local_teid' and 'remote_teid'")
        
        teid_list.append({
            "local_teid": int(entry["local_teid"]),
            "remote_teid": int(entry["remote_teid"])
        })
    
    # Limit to 10 TEID pairs
    if len(teid_list) > 10:
        teid_list = teid_list[:10]
        print("⚠️  TEID list truncated to 10 entries (max allowed)")

    return teid_list

def send_gtpu_packets(local_ip, remote_ip, teid_file, direction, payload_size):
    """Main loop to send GTP-U packets for all TEID pairs"""
    teid_list = load_teids_from_file(teid_file)
    if not teid_list:
        print("[ERROR] No valid TEID pairs found in file.")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((local_ip, GTPU_PORT))
    print(f"[INFO] Bound to {local_ip}:{GTPU_PORT}")
    print(f"[INFO] Sending to {remote_ip}:{GTPU_PORT}")
    print(f"[INFO] Loaded {len(teid_list)} TEID pairs")

    SO_MARK = 36  # socket option for mark


    payload = bytes(random.getrandbits(8) for _ in range(payload_size))
    counter = 0

    try:
        while running:
            #for local_teid, remote_teid in teid_pairs:
            for pair in teid_list:
                local_teid = pair["local_teid"]
                remote_teid = pair["remote_teid"]
                #packet = build_gtpu_packet(local_teid, remote_teid, payload)
                packet = build_gtpu_packet(local_teid, remote_teid, payload, direction="uplink")
                packet = build_gtpu_packet(local_teid, remote_teid, payload, direction)
                sock.setsockopt(socket.SOL_SOCKET, SO_MARK, remote_teid)
                sock.sendto(packet, (remote_ip, GTPU_PORT))
                counter += 1
                print(f"[{counter}] Sent GTP-U packet: Local TEID={local_teid}, Remote TEID={remote_teid}, Size={payload_size} bytes")
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print(f"[INFO] Total packets sent: {counter}")
        print("[INFO] GTP-U sender exited cleanly.")

def main():
    parser = argparse.ArgumentParser(description="Send GTP-U packets continuously with TEID pairs.")
    parser.add_argument("--local-ip", required=True, help="Local IP address to bind")
    parser.add_argument("--remote-ip", required=True, help="Remote IP address to send packets to")
    parser.add_argument("--teid-file", required=True, help="File containing TEID pairs (max 10 lines)")
    parser.add_argument("--direction", required=True, help="Direction uplink or downlink ")
    parser.add_argument("--payload-size", type=int, default=64, help="Size of dummy payload in bytes")
    args = parser.parse_args()

    send_gtpu_packets(args.local_ip, args.remote_ip, args.teid_file, args.direction, args.payload_size)

if __name__ == "__main__":
    main()

