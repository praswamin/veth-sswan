from scapy.all import sniff, UDP
import json
import time

gtpu_port = 2152
gtpu_stats = {"sent": 0, "received": 0}

def count_gtpu_packet(pkt):
    global gtpu_stats
    if UDP in pkt and (pkt[UDP].sport == gtpu_port or pkt[UDP].dport == gtpu_port):
        if pkt[UDP].sport == gtpu_port:
            gtpu_stats["sent"] += 1
        else:
            gtpu_stats["received"] += 1

def monitor_gtpu(interface="vethA-hostA", duration=10):
    print(f"[*] Monitoring GTP-U packets on {interface} for {duration}s...")
    sniff(iface=interface, filter=f"udp port {gtpu_port}", prn=count_gtpu_packet, timeout=duration)
    print(f"\nSummary for {interface}:")
    print(json.dumps(gtpu_stats, indent=2))

if __name__ == "__main__":
    try:
        while True:
            gtpu_stats = {"sent": 0, "received": 0}
            monitor_gtpu(interface="vethA-hostA", duration=5)
            print(f"Total GTP-U packets in last 5s: {gtpu_stats}")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[+] Exiting GTP-U monitor.")

