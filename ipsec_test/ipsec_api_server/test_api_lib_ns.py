#!/usr/bin/env python3
import subprocess
import json
import uuid
from flask import Flask, jsonify, request, Response
import re
import os
import psutil
import socket
from tabulate import tabulate
import test_api_renderer

HOST_PATH = os.environ['HOST_IPSEC_DIR']
print(f"HOST_PATH: {HOST_PATH}")


# Global state to track existing configuration info
CONFIG_STATE = {
    "hostA": {
        "connection_name": "net-test",
        "local_ip": "10.200.1.10",
        "remote_ip": "10.200.2.20",
        "local_id": "hostA",
        "remote_id": "hostB",
        "children": [
            {"name": "net", "local_ts": "10.10.0.1/28", "remote_ts": "10.10.1.1/28"}
        ]
    },
    "hostB": {
        "connection_name": "net-test",
        "local_ip": "10.200.2.20",
        "remote_ip": "10.200.1.10",
        "local_id": "hostB",
        "remote_id": "hostA",
        "children": [
            {"name": "net", "local_ts": "10.10.1.1/28", "remote_ts": "10.10.0.1/28"}
        ]
    }
}

def run_cmd(cmd):
    result = subprocess.run(
        "sudo " + cmd,
        shell=True,
        capture_output=True,
        text=True
    )
    #print(f"cmd in run_cmd is {cmd}")
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
        "--uri",  uri
    ]

    if swanctl_cmd == "--list-sas":
        cmd += ["--raw"]

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
    if proc.pid is None:
        raise RuntimeError(f"Failed to start process in namespace {ns}")
    else:
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
    Updated to handle whitespace around '='.
    """
    # Fix: Pre-process the string to remove spaces around equals signs [Conversation History]
    raw = re.sub(r'\s*=\s*', '=', raw)

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
            if stack: stack.pop()
            current = stack[-1] if stack else root
        elif "=" in token:
            k, v = token.split("=", 1)
            current[k] = v.strip("[]")
        else:
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
        print(f"Running the script {script_path}")
        setup_result = run_cmd(f"{script_path}")
        if setup_result["returncode"] != 0:
            return False, {
                "status": "error",
                "message": "Infrastructure script failed"
            }
        
        
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

   
def add_ns_ip(ns, ip_addr, interface):
    """
    Adds an IP address to a specific interface inside a namespace.
    Utilizes run_in_ns to ensure execution within the correct shell context.
    """
    # 1. Construct the internal command string
    # run_in_ns will wrap this with the appropriate namespace entry command
    cmd = f"ip addr add {ip_addr} dev {interface}"
    
    # 2. Execute via the shell-aware run_in_ns helper
    result = run_in_ns(ns, cmd)
    
    # 3. Standardized Driver Return (bool, dict) for api_server.py unpacking 
    if result["rc"] == 0:
        return True, {
            "status": "success",
            "message": f"Successfully added {ip_addr} to {interface} in namespace {ns}",
            "stdout": result["stdout"]
        }
    elif "File exists" in result["stderr"]:
        # Idempotency: IP is already assigned, so we treat it as a success 
        return True, {
            "status": "already_exists",
            "message": f"IP address {ip_addr} is already present on {interface} in {ns}"
        }
    else:
        return False, {
            "status": "error",
            "message": f"Failed to add IP address: {result['stderr']}",
            "rc": result["rc"]
        }  

    
# def update_ns_swanctl(ns, config_text, vici_socket=None):
#     """
#     Updates the swanctl.conf for a namespace and reloads the configuration.
#     Utilizes run_swanctl_in_ns for precise namespace and VICI socket control [1].
#     """
#     # 1. Define the host-side path for the configuration file
#     conf_path = f"/etc/ipsec-ns/{ns}/swanctl/swanctl.conf"
    
#     # 2. Write the new configuration to the file using the run_cmd helper
#     write_cmd = f"tee {conf_path} <<'EOF'\n{config_text}\nEOF"
#     write_result = run_cmd(write_cmd)
    
#     if write_result["returncode"] != 0:
#         return False, {
#             "status": "error",
#             "message": f"Failed to write swanctl config to {conf_path}",
#             "stderr": write_result["stderr"]
#         }

#     # 3. Reload configuration using run_swanctl_in_ns 
#     # This helper returns a tuple: (stdout, stderr, rc)
#     try:
#         # We pass "load-all" as the command string
#         stdout, stderr, rc = run_swanctl_in_ns(ns, "--load-all", vici_socket=vici_socket)
        
#         if rc == 0:
#             return True, {
#                 "status": "success",
#                 "message": f"Updated and reloaded swanctl config for {ns}",
#                 "stdout": stdout.strip()
#             }
#         else:
#             return False, {
#                 "status": "error",
#                 "message": f"Config written but swanctl load failed for {ns}",
#                 "stderr": stderr.strip(),
#                 "rc": rc
#             }
#     except Exception as e:
#         return False, {
#             "status": "error",
#             "message": f"Unexpected error during swanctl reload: {str(e)}"
#         }

def update_ns_swanctl(ns, new_params, vici_socket=None):
    """
    Appends new children to existing config and re-renders swanctl.conf.
    """
    if ns not in CONFIG_STATE:
        return False, {"status": "error", "message": f"Namespace {ns} not initialized in CONFIG_STATE"}

    # 1. Retrieve the 'Existing' info for this host
    current_config = CONFIG_STATE[ns]

    # 2. Append NEW children if provided [History]
    new_children = new_params.get("children", [])
    if new_children:
        # Check for duplicates by name to prevent redundant blocks
        existing_names = {child['name'] for child in current_config["children"]}
        for child in new_children:
            if child['name'] not in existing_names:
                current_config["children"].append(child)

    # 3. Update other fields if connection_name changes
    if "connection_name" in new_params:
        current_config["connection_name"] = new_params["connection_name"]

    # 4. Render the configuration using ALL info (existing + new) [1]
    try:
        config_text = test_api_renderer.render_swanctl(current_config)
    except Exception as e:
        return False, {"status": "error", "message": f"Rendering failed: {str(e)}"}

    # 5. Apply the configuration (Logic from Source 290)
    conf_path = f"/etc/ipsec-ns/{ns}/swanctl/swanctl.conf"
    try:
        with open("/tmp/temp_swanctl.conf", "w") as f:
            f.write(config_text)
        run_cmd(f"cp /tmp/temp_swanctl.conf {conf_path}")
        
        #success, load_res = ns_ipsec_load(ns)
        stdout, stderr, rc = run_swanctl_in_ns(ns, "--load-all", vici_socket=vici_socket)
        if rc == 0:
            return True, {
                "status": "success",
                "message": f"Updated and reloaded swanctl config for {ns}",
                "stdout": stdout.strip()
            }
        else:
            return False, {
                "status": "error",
                "message": f"Config written but swanctl load failed for {ns}",
                "stderr": stderr.strip(),
                "rc": rc
            }
    except Exception as e:
        return False, {
            "status": "error",
            "message": f"Unexpected error during swanctl reload: {str(e)}"
        }



def ns_cleanup():
    script_path = f"{HOST_PATH}/ipsec_ns_cleanup.sh"

    #  Run cleanup script
    cleanup_result = run_cmd(f"{script_path}")

    if cleanup_result["returncode"] != 0:
        return False, {
            "status": "error",
            "message": f"Failed to run cleanup script",
            "stderr": cleanup_result["stderr"]
        }
    else:
        return True, {
            "status": "success",
            "message": "Cleanup completed successfully",
            "stdout": cleanup_result["stdout"]
        }

def get_ns_veth_info(ns=None, ifname=None):
    """
    Retrieves and filters veth interface details from the current environment.
    Follows the (bool, dict) return pattern for seamless api_server.py integration [History].
    """
    try:
        # 1. Fetch the raw list of interface rows 
        # This executes 'ip netns list' and 'ip link' commands internally.
        rows = collect_veth_table()
        
        # 2. Use the existing formatting helper with an optional namespace filter 
        # result.append({"namespace": ns, "interface": ifname, "state": state, ...})
        data = format_veth_rows(rows, get_ns=ns)
        
        # 3. Apply an additional interface name filter if requested
        if ifname:
            data = [item for item in data if ifname in item["interface"]]
            
        return True, {
            "status": "success",
            "message": f"Retrieved {len(data)} interface(s)",
            "data": data
        }
    except Exception as e:
        return False, {
            "status": "error",
            "message": f"Failed to retrieve networking state: {str(e)}"
        }

def ns_init_host(ns=None):
    """
    Initialises a host within the specified namespace.
    Follows the (bool, dict) return pattern for seamless api_server.py integration
    """
    try:
              
        script_path = f"{HOST_PATH}/ipsec-ns"
        #hosts = ["hostA", "hostB"]
        script_path = f"{HOST_PATH}/ipsec-ns"
        script = f"{script_path}/{ns}/init-{ns}.sh"
        setup_result = run_in_ns(ns, script)

    #status = "success" if setup_result["rc"] == 0 else "failure"
    
        if setup_result["rc"] == 0:
            return True, {
                "status": "success",
                "message": f"Initialised {ns}",
                "stdout": setup_result["stdout"]
            }
        else:
            return False, {
                "status": "error",
                "message": f"Unable to initialise {ns}",
                "stderr": setup_result["stderr"],
                "rc": setup_result["rc"]
            }
    except Exception as e:
        return False, {
            "status": "error",
            "message": f"Unexpected error during Initialising of host {ns}: {str(e)}"
        }


def ns_ipsec_load(ns=None, vici_socket=None):
    """
    Loads IPsec configuration on a host within the specified namespace.
    Follows the (bool, dict) return pattern for seamless api_server.py integration
    """
    try:
        #out, err, rc = run_ns(ns, ["swanctl", "--load-all"])
        load_all, err, rc = run_swanctl_in_ns(ns, "--load-all", vici_socket)

        loaded, failed = [], []

        for line in load_all.splitlines():
            l = line.lower()
            if "loaded" in l:
                loaded.append(line.strip())
            if "failed" in l or "error" in l:
                failed.append(line.strip())

        #status = "success" if rc == 0 and not failed else "partial-failure"

        if rc == 0:
            return True, {
                "status": "success",
                "message": f"Loaded IPsec configuration for {ns}",
                "loaded": loaded,
                "failed": failed
            }
        else:
            return False, {
                "status": "error",
                "message": f"Failed to load IPsec configuration for {ns}",
                "loaded": loaded,
                "failed": failed,
                "stderr": err.strip() if err else None
            }
    except Exception as e:
        return False, {
            "status": "error",
            "message": f"Unexpected error during IPsec configuration loading for {ns}: {str(e)}"
        }
    
def get_ns_stats(ns=None, format_type="table", vici_socket=None):
    """
    Extracts the IPsec statistics on a host within the specified namespace.
    Follows the (bool, dict) return pattern for seamless api_server.py integration
    """
    
    # run_swanctl_in_ns handles the nsenter (net/mount) context 
    cmd = "--list-sas"
    stdout, stderr, rc = run_swanctl_in_ns(ns, cmd, vici_socket=vici_socket)
    
    if rc != 0:
        return False, {
           "status": "error",
            "message": f"Failed to retrieve stats for namespace: {ns}",
            "stderr": stderr
        }

    #print(stdout)
    # 2. Parse the raw VICI output into a structured dictionary 
    try:
        parsed_data = parse_vici(stdout)
        # Convert parsed IKE/Child SA data into tabular rows
        print(f"Parsed Data: {parsed_data}") 

        #wrapped_data = {"event": parsed_data}
    
        # Now sas_to_table will see the SAs under the 'event' key
        rows = sas_to_table(parsed_data)        
        
        # 3. Handle requested output format
        if format_type == "table":
            print(f"Rows: {rows}")
            headers = [
                "Connection", "IKE State", "Child SA", "Child State", "Protocol", "Mode", 
                "SPI-In", "SPI-Out", "Pkts-In", "Pkts-Out", "Bytes-In", "Bytes-Out",
                "Local-TS", "Remote-TS", "Local-Host", "Remote-Host"
            ]
            # sas_to_table returns 18 columns; we use the first 16 for standard display 
            table_str = tabulate([row[:16] for row in rows], headers=headers, tablefmt="grid")
            print(f"Table: {table_str}")
            
            return True, {
                "status": "success",
                "output": table_str
            }
        else:
            # Return raw list of dictionaries for JSON-native clients
            # Maps the 18 columns from sas_to_table to named keys 
            keys = [
                "ike_name", "ike_state", "child_name", "child_state", "protocol", "mode", 
                "spi_in", "spi_out", "packets_in", "packets_out", "bytes_in", "bytes_out",
                "local_ts", "remote_ts", "local_host", "remote_host", "ike_spi_i", "ike_spi_r"
            ]
            stats_list = [dict(zip(keys, row)) for row in rows]
            
            return True, {
                "status": "success",
                "data": stats_list
            }

    except Exception as e:
        return False, {
            "status": "error", 
            "message": f"Error parsing stats for {ns}: {str(e)}"
        }

def add_ns_child(ns, ike, child_name, vici_socket=None):
    """
    Initiates a specific Child SA within a namespace.
    Equivalent to: swanctl --initiate --child <child_name> [1, 3].
    """
    # 1. Define the initiation arguments
    args = ["--initiate", "--ike", ike, "--child", child_name]
    
    # 2. Execute via the shell-aware run_swanctl helper
    # This helper handles nsenter and VICI socket path resolution 
    try:
        result = run_swanctl(ns, args)
        
        # 3. Standardized Driver Return (bool, dict) 
        if result.returncode == 0:
            return True, {
                "status": "success",
                "message": f"Successfully initiated child SA '{child_name}' in namespace {ns}",
                "stdout": result.stdout.strip()
            }
        else:
            return False, {
                "status": "error",
                "message": f"Failed to initiate child SA: {result.stderr.strip()}",
                "rc": result.returncode
            }
    except Exception as e:
        return False, {
            "status": "error",
            "message": f"Unexpected error during child initiation: {str(e)}"
        }

import time
import json

def run_ns_iperf_server(server_ns, bind_ip, port, logfile, pidfile):
    """
    Executes an iperf3 test between two namespaces.
    1. Starts a one-shot server in the background.
    2. Runs a client in the foreground and captures JSON output.
    """
    # 1. Start iperf3 server in the background (-s) for one-off connection (-1)
    # Using run_ns_bg to prevent blocking the execution thread [1]
    try:
                
        #server_cmd = ["iperf3", "-s", "-1", "-p", str(port)]
        
        server_cmd = [
            "iperf3",
            "-s",
            "-B", bind_ip,
            "-p", str(port),
            "--daemon",
            "--logfile", logfile,
            "--pidfile", pidfile
        ]
        
        pid = run_ns_bg(server_ns, server_cmd)
        
        # Brief pause to ensure the server socket is listening
        time.sleep(1)
                # 2. Run iperf3 client in the foreground (-c) with JSON output (-J)
        # Using run_in_ns to ensure proper namespace entry [2]
        # simple sanity delay
    
        return True, {
            "status": "success",
            "message": f"iperf3 server started in namespace {server_ns}",
            "details": {
                "pid": pid,
                "port": port                
            }
        }
    except Exception as e:
        return False, {"status": "error", "message": f"Failed to start server: {str(e)}"}

def check_ns_iperf_status(ns, port):
    """
    Verifies if an iperf3 server is actually listening on the specified port.
    Returns: (bool, str) status and detail.
    """
    # Use 'ss -ltn' to check for listening TCP sockets on the specific port
    # In Docker mode, this translates to: docker exec <ns> ss -ltn sport == :<port>
    # In NS mode, this translates to: ip netns exec <ns> ss -ltn sport == :<port>
    cmd = f"ss -ltn sport == :{port}"
    
    try:
        # Utilize the appropriate exec helper (docker_exec or run_in_ns)
        # Assuming Docker mode for this example:
        result = docker_exec(ns, cmd) 
        
        # Check if the port appears in the output
        is_listening = (result["returncode"] == 0 and str(port) in result["stdout"])
        
        return is_listening, "LISTENING" if is_listening else "STOPPED"
    except Exception as e:
        return False, f"ERROR: {str(e)}"

def run_ns_iperf_client(ns, server_ip, protocol, port=5201, bandwidth=None, duration=5, logfile=None):
    """
    Runs an iperf3 client in the background and returns structured JSON results.
    """
    # -c: client, -p: port, -t: time 
    cmd = ["iperf3", "-c", server_ip, "-t", str(duration), "-p", str(port), "-J"]

    if protocol == "udp":
        cmd += ["-u"]
        if bandwidth:
            cmd += ["-b", bandwidth]
    elif protocol == "sctp":
        cmd += ["--sctp"]
    #cmd = f"iperf3 -c {server_ip} -p {port} -t {duration} -J"
    
    try:
        # run_in_ns handles namespace entry via nsenter [1]
        pid = run_ns_bg(ns, cmd, logfile)
        
        if pid is not None:
            # Parse results for the Model Context Protocol (MCP) layer [76, History]
            #report = json.loads(result["stdout"])
            return True, {
                "status": "success",
                "message": "Traffic test started",
                "tool": "iperf",
                "protocol": protocol,
                "server": server_ip,
                "pid": pid,
                "log": logfile,
                "status": "started"
            }
        else:
            return False, {
                "status": "error", 
                "message": "iperf3 client failed to connect",
                "status": "failed"
            }
    except Exception as e:
        return False, {"status": "error", "message": f"Execution error: {str(e)}"}

def start_ns_gtpu_server(ns, local_ip, remote_ip, teid_file, direction, payload_size, logfile=None):
    """
    Starts a GTP-U listener in the background inside a namespace.
    """
    cmd = [
        "python3",
        f"{HOST_PATH}/traffic/new_gtp_udp_send.py",
        "--local-ip", local_ip,
        "--remote-ip", remote_ip,
        "--teid-file", teid_file,
        "--direction", direction,
        "--payload-size", str(payload_size)
       ]
    
    try:
        # run_in_ns handles namespace entry via nsenter [1]
        pid = run_ns_bg(ns, cmd, logfile)
        
        if pid is not None:
            return True, {
                "status": "success",
                "namespace": ns,
                "tool": "gtpu",
                "direction": direction,
                "pid": pid,
                "log": logfile,
                "status": "started"
            }
        else:
            return False, {
                "status": "error", 
                "message": "iperf3 client failed to connect",
                "status": "failed"
            }
    except Exception as e:
            return False, {"status": "error", "message": f"Execution error: {str(e)}"}

def terminate_ns_child(ns, child_name, ike_name=None):
    """
    Terminates a specific Child SA within a namespace.
    Equivalent to: swanctl --terminate --child <child_name>.
    """
    # 1. Define termination arguments
    # The --child flag targets the specific security association [1]
    args = ["--terminate", "--child", child_name]
    if ike_name:
        args.extend(["--ike", ike_name])

    # 2. Execute via the established run_swanctl helper
    try:
        result = run_swanctl(ns, args)
        
        # 3. Standardized Driver Return (bool, dict) [295, History]
        if result.returncode == 0:
            return True, {
                "status": "success",
                "message": f"Successfully terminated child SA '{child_name}' in namespace {ns}",
                "stdout": result.stdout.strip()
            }
        else:
            return False, {
                "status": "error",
                "message": f"Failed to terminate child SA: {result.stderr.strip()}",
                "rc": result.returncode
            }
    except Exception as e:
        return False, {
            "status": "error",
            "message": f"Unexpected error during child termination: {str(e)}"
        }


def stop_ns_gtpu_server(ns, pid):
    """
    Stops a GTP-U listener in the background inside a namespace.
    """
    cmd = f"kill -SIGINT {pid}"
    print(f"cmd: {cmd}")


    try:
        result = run_in_ns(ns, cmd)
        if result["rc"] == 0:
            return True, {
                "status": "success",
                "message": f"Successfully stopped GTP-U server in namespace {ns}",
                "stdout": result["stdout"]
            }
        else:
            return False, {
                "status": "error",
                "message": f"Failed to stop GTP-U server: {result['stderr']}",
                "rc": result["rc"]
            }
    except Exception as e:  
        return False, {
            "status": "error",
            "message": f"Unexpected error during GTP-U server termination: {str(e)}"
        }  
    

def check_ns_loopback_ping(src_ns, src_loopback, dst_loopback, count=4):
    """
    Pings from one host's loopback to another's to verify the IPsec tunnel.
    Command: ip netns exec <src_ns> ping -I <src_loopback> -c <count> <dst_loopback>
    """
    # -I: specifies the source interface/IP
    # -W 2: wait 2 seconds for a response
    cmd = f"ping -I {src_loopback} -c {count} -W 2 {dst_loopback}"
    
    try:
        # run_in_ns handles the nsenter/netns execution context
        result = run_in_ns(src_ns, cmd)
        
        if result["rc"] == 0:
            return True, {
                "status": "success",
                "message": f"IPsec Connectivity Verified: {src_ns} reached {dst_loopback}",
                "stdout": result["stdout"]
            }
        else:
            return False, {
                "status": "error",
                "message": "Tunnel verification failed: Destination unreachable",
                "stderr": result["stderr"]
            }
    except Exception as e:
        return False, {"status": "error", "message": f"Ping execution error: {str(e)}"}