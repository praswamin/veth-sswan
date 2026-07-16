#!/usr/bin/env python3
import subprocess
import json
from flask import Flask, jsonify, request, Response
import re
import os
import psutil
import socket
from tabulate import tabulate

HOST_PATH = os.environ['HOST_IPSEC_DIR']
print(f"HOST_PATH: {HOST_PATH}")

def run_cmd(cmd):
    result = subprocess.run(
        "sudo " + cmd,
        shell=True,
        capture_output=True,
        text=True
    )
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip()
    }

def collect_ip_addr(ns):
    """
    Returns:
      {
        "vethA": {"ipv4": [...], "ipv6": [...]},
        "lo":    {"ipv4": [...], "ipv6": [...]}
      }
    """
    result = run_cmd(f"ip netns exec {ns} ip -br addr")
    addr_map = {}

    for line in result["stdout"].splitlines():
        parts = line.split()
        iface = parts[0]
        addrs = parts[2:] if len(parts) > 2 else []

        ipv4 = [a for a in addrs if "." in a]
        ipv6 = [a for a in addrs if ":" in a]

        addr_map[iface] = {
            "ipv4": ipv4,
            "ipv6": ipv6
        }

    return addr_map

def get_ip_addr_map(ns):
    cmd = f"ip netns exec {ns} ip -br addr"
    result = run_cmd(cmd)

    addr_map = {}

    if result["returncode"] != 0:
        return addr_map

    for line in result["stdout"].splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue

        iface = parts[0]
        addrs = parts[2:]

        ipv4 = []
        ipv6 = []

        for addr in addrs:
            if ":" in addr:
                ipv6.append(addr)
            else:
                ipv4.append(addr)

        addr_map[iface] = {
            "ipv4": ipv4,
            "ipv6": ipv6
        }

    return addr_map

def collect_veth_table():

    ns_result = run_cmd("ip netns list")
    namespaces = []

    rows = []
    for line in ns_result["stdout"].splitlines():
        ns = line.split()[0]
        namespaces.append(ns)
        print(f"Extracting details for {ns}")

        # Get interface addresses
        addr_map = get_ip_addr_map(ns)

        # Get link info
        cmd = f"ip netns exec {ns} ip -o link"
        result = run_cmd(cmd)

        if result["returncode"] != 0:
            return rows

        for line in result["stdout"].splitlines():
            # Example:
            # 10: vethA@if9: <BROADCAST,MULTICAST,UP,LOWER_UP> ...
            parts = line.split(":")
            if len(parts) < 3:
                continue

            ifname = parts[1].strip()
            flags = parts[2]

            # Only show veth interfaces
            if not ifname.startswith("veth"):
                continue

            ipv4 = ", ".join(addr_map.get(ifname, {}).get("ipv4", [])) or "-"
            ipv6 = ", ".join(addr_map.get(ifname, {}).get("ipv6", [])) or "-"

            state = "UP" if "UP" in flags else "DOWN"

            rows.append([
                ns,
                ifname,
                state,
                ipv4,
                ipv6
            ])
            #print(f"Rows is {rows} and length is {len(rows)}")
    return rows

def veth_setup_exists(rows, ns_a, ns_b, if_a, if_b):
    """
    Check if required namespace + veth interfaces exist
    """
    found_a = False
    found_b = False

    for row in rows:
        ns, ifname, state, ipv4, ipv6 = row

        if ns in ns_a and if_a in ifname:
            found_a = True

        if ns in ns_b and if_b in ifname:
            found_b = True
    print(f"Found {ns_a}:{if_a}={found_a}, {ns_b}:{if_b}={found_b}")
    
    return found_a and found_b

def format_veth_rows(rows, get_ns=None):
    result = []

    for row in rows:
        ns, ifname, state, ipv4, ipv6 = row

        if get_ns and ns != get_ns:
            continue

        result.append({
            "namespace": ns,
            "interface": ifname,
            "state": state,
            "ipv4": ipv4,
            "ipv6": ipv6
        })

    return result


def run_in_ns(ns, cmd):
    if isinstance(cmd, str):
        exec_cmd = ["bash", "-lc", cmd]
    else:
        exec_cmd = list(cmd)

    try:
        pid = get_ns_pid(ns)
        proc = subprocess.run(
            ["sudo", "nsenter", "-t", pid, "-n", "-m"] + exec_cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )
    except Exception:
        proc = subprocess.run(
            ["sudo", "ip", "netns", "exec", ns] + exec_cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30
        )

    return {
        "rc": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()
    }


def sigint_ns_process(ns: str, pid: int):
    """
    Send Ctrl+C (SIGINT) to a process inside a namespace.
    """
    subprocess.run(
        ["sudo", "ip", "netns", "exec", ns, "kill", "-INT", str(pid)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

def get_ns_pid(ns_name):
    """
    Get one PID that is currently inside the given network namespace
    """
    result = subprocess.run(
        ["sudo", "ip", "netns", "pids", ns_name],
        capture_output=True,
        text=True,
        check=True
    )
    pids = result.stdout.strip().splitlines()
    if not pids:
        raise RuntimeError(f"No processes found in namespace {ns_name}")
    return pids[0]


def get_vici_socket_path(ns_name):
    """Read the VICI socket path from the namespace's strongSwan config."""
    try:
        cfg = run_in_ns(ns_name, "cat /etc/strongswan.conf")
    except Exception:
        cfg = {"stdout": "", "rc": 1}

    if cfg.get("rc", 1) == 0:
        match = re.search(r"socket\s*=\s*(unix://\S+)", cfg.get("stdout", ""))
        if match:
            return match.group(1).replace("unix://", "")

    return f"/etc/ipsec.d/run/charon-{ns_name}.vici"


def run_swanctl_in_ns(ns_name, swanctl_cmd, vici_socket=None):
    """
    Execute swanctl inside a namespace using nsenter (net + mount)
    """
    pid = get_ns_pid(ns_name)
    print(f"process id: {pid}")

    if not vici_socket:
        vici_socket = get_vici_socket_path(ns_name)

    uri = vici_socket if vici_socket.startswith("unix://") else f"unix://{vici_socket}"

    cmd = [
        "sudo",
        "nsenter",
        "-t", pid,
        "-n",   # network namespace
        "-m",   # mount namespace
        "swanctl",
        swanctl_cmd,
        "--raw",
        "--uri",  uri
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )

    #if result.returncode != 0:
    #    raise RuntimeError(result.stderr.strip())

    #if not result.stdout.strip():
    #    raise RuntimeError(f"swanctl returned empty stdout, stderr={proc.stderr}")

    #return result.stdout
    return result.stdout, result.stderr, result.returncode

def run_ns_bg(ns: str, cmd: list[str], logfile: str | None = None):
    """
    Run a command in a namespace fully detached.
    If logfile is None, stdout/stderr are discarded.
    """
    stdout_target = subprocess.DEVNULL
    stderr_target = subprocess.DEVNULL

    if logfile:
        lf = open(logfile, "a")
        stdout_target = lf
        stderr_target = lf

    proc = subprocess.Popen(
        ["sudo", "ip", "netns", "exec", ns] + cmd,
        stdin=subprocess.DEVNULL,
        stdout=stdout_target,
        stderr=stderr_target,
        start_new_session=True
    )

    return proc.pid


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_swanctl(ns, args):

    vici_socket = get_vici_socket_path(ns)
    
    pid = get_ns_pid(ns)
    print(f"process id: {pid}")

    cmd = [
        "sudo",
        "nsenter",
        "-t", pid,
        "-n",   # network namespace
        "-m",   # mount namespace
        "swanctl"
    ] + args

    if vici_socket:
        cmd.extend(["--uri", vici_socket if vici_socket.startswith("unix://") else f"unix://{vici_socket}"])

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )



import re

def parse_vici(raw):
    """
    Generic parser for strongSwan VICI text output.
    Works for all swanctl --raw commands.
    """

    stack = []
    root = {}
    current = root
    key_stack = []

    tokens = re.findall(r'\{|\}|\[[^\]]*\]|[^\s{}]+', raw)

    for token in tokens:
        if token == "{":
            new_obj = {}
            if key_stack:
                parent = stack[-1] if stack else root
                parent[key_stack.pop()] = new_obj
            stack.append(new_obj)
            current = new_obj

        elif token == "}":
            stack.pop()
            current = stack[-1] if stack else root

        elif "=" in token:
            k, v = token.split("=", 1)
            current[k] = v.strip("[]")

        else:
            # block name (e.g., net-test, net-1, list-sa, list-pols)
            key_stack.append(token)

    return root

def sas_to_table(parsed):
    """
    Convert parsed VICI list-sas output to tabular rows.
    One row per CHILD SA.
    """

    rows = []

    events = parsed.get("event", {})

    for ike_name, ike in events.items():
        ike_state = ike.get("state", "")
        local_host = ike.get("local-host", "")
        remote_host = ike.get("remote-host", "")
        initiator_spi = ike.get("initiator-spi", "")
        responder_spi = ike.get("responder-spi", "")

        children = ike.get("child-sas", {})

        for child_id, child in children.items():
            rows.append([
                ike_name,
                ike_state,
                child.get("name", child_id),
                child.get("state", ""),
                child.get("protocol", ""),
                child.get("mode", ""),
                child.get("spi-in", ""),
                child.get("spi-out", ""),
                int(child.get("packets-in", 0)),
                int(child.get("packets-out", 0)),
                int(child.get("bytes-in", 0)),
                int(child.get("bytes-out", 0)),
                child.get("local-ts", ""),
                child.get("remote-ts", ""),
                local_host,
                remote_host,
                initiator_spi,
                responder_spi
            ])

    return rows

def init_setup(format_type="table"):
    """
    Namespace-specific initialization.
    Handles script execution and state collection.
    """
    # Move namespace and interface definitions here 
    ns_a = "hostA"
    ns_b = "hostB"
    if_a = "vethA-hostA"
    if_b = "vethB-hostB"

    # Format response
    #as_table = request.args.get("format", "table") == "table"
    as_table = (format_type == "table")


    #1. ---- Collect current state ----
    try:
        rows = collect_veth_table()
    except Exception as e:
        return False, {"status": "error", "message": str(e)} 

    
    # ---- Check if setup already exists ----
    if veth_setup_exists(rows, ns_a, ns_b, if_a, if_b):
        return True, {
            "status": "already_exists",
            "message": "Namespace and veth setup already present",
            "existing_entries": rows
        }
    
    

    # 2. Execute the infrastructure shell script 
    script_path = f"{HOST_PATH}/ipsec_ns_setup.sh"
    if not os.path.isfile(script_path):
        return False, {
            "status": "error",
            "message": "Infrastructure script not found"
        }

    try:
        # Runs the automated namespace and veth-pair setup
        #subprocess.run(["sudo", "bash", "./ipsec_ns_setup.sh"], check=True)
        setup_result = run_cmd(f"{script_path}")
    except Exception as e:
        return False, {
            "status": "error",
            "message": "Infrastructure script failed",
            "details": str(e)
        }



    # 3. Collect current state to verify setup 
    try:
        veth_table = collect_veth_table()
        if as_table:
        table_str = tabulate(
            veth_table,
            headers=["Namespace", "Interface", "State", "IPv4 Address", "IPv6 Address"],
            tablefmt="grid"
        )

        return True, {
            "status": "success",
            "message": f"IPsec Namespace Setup Successful\n\n{table_str}\n",
            "veths": [
                dict(ns=row[0], ifname=row[1], state=row[2], ipv4=row[4], ipv6=row[5])
                for row in veth_table
            ]
        }
    except Exception as e:
        return False, {
            "status": "error",
            "message": "Infrastructure ready, but failed to collect veth table",
            "stdout": setup_result["stdout"],
            "stderr": setup_result["stderr"]
        }

   
    

    
       