#!/usr/bin/env python3
import subprocess
import json
import os
import socket
from tabulate import tabulate
import test_api_renderer  # Import the renderer module for swanctl.conf rendering
import time
import sys

# Global Configuration
#HOST_PATH = os.environ.get('HOST_IPSEC_DIR', '/home/prash/veth-sswan-docker/ipsec_test/')
#HOST_PATH = os.environ.get('HOST_IPSEC_DIR', '/home/prash/veth-sswan-docker/ipsec_test/')
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
    """Local shell helper."""
    result = subprocess.run("sudo -E " + cmd, shell=True, capture_output=True, text=True)
    return {
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip()
    }


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def docker_exec(container, cmd):
    """Helper to execute commands inside a Docker container."""
    full_cmd = f"docker exec {container} {cmd}"
    return run_cmd(full_cmd)

# def init_setup(format_type="table"):
#     """
#     Docker-specific initialization. 
#     Triggers the docker-compose or container setup script.
#     """
#     script_path = f"{HOST_PATH}/ipsec_docker_setup.sh"
#     if not os.path.isfile(script_path):
#         return False, {"status": "error", "message": f"Setup script not found at {script_path}"}

#     setup_result = run_cmd(f"bash {script_path}")
#     if setup_result["returncode"] != 0:
#         return False, {"status": "error", "message": "Docker setup failed", "stderr": setup_result["stderr"]}

#     # Collect state (Placeholder for docker container list)
#     return True, {"status": "success", "message": "Docker IPsec lab initialized", "veths": []}


def collect_container_table():
    """
    Collects metadata for the core Docker containers in the lab.
    Returns: A list of dictionaries containing name, short ID, and state.
    """
    expected_nodes = ["hostA", "router", "hostB"]
    container_info = []
    
    for node in expected_nodes:
        # We use Go-template formatting to get the ID and Status in one call
        res = run_cmd(f"docker inspect -f '{{{{.Id}}}},{{{{.State.Status}}}}' {node}")
        
        if res["returncode"] == 0:
            # Split the comma-separated output
            parts = res["stdout"].split(",")
            full_id = parts
            status = parts[1]
            
            container_info.append({
                "name": node,
                "id": full_id[:12],  # Use the short 12-character ID
                "state": status.upper()
            })
            
    return container_info

def init_setup(format_type="table"):
    """
    Docker-specific initialization. 
    Triggers 'ipsec_docker_setup.sh' and returns live container metadata.
    """
    # 1. Path to the modern setup script using 'docker compose'
    mode = os.environ.get('LAB_MODE', 'docker')  # Default to 'docker' if not set
    script_name = "ipsec_ns_setup.sh" if mode == 'ns' else "ipsec_docker_setup.sh" 
    script_path = f"{HOST_PATH}/{script_name}"
    
    if not os.path.isfile(script_path):
        return False, {"status": "error", "message": f"Setup script not found at {script_path}"}

    # # 2. Execute script and verify return code (Fixes silent failures)
    # setup_result = run_cmd(f"bash {script_path}")
    # if setup_result["returncode"] != 0:
    #     return False, {
    #         "status": "error", 
    #         "message": "Docker setup failed", 
    #         "stderr": setup_result["stderr"]
    #     }
    
    # 2. Start the process in the background using Popen
   
    print(f"[+] Executing {script_name}", end=" ", flush=True)
    proc = subprocess.Popen(
        ["sudo", "bash", script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

     # 3. Polling Loop: Dots and Timeout logic
    start_time = time.time()
    dot_count = 0
    timeout = 180  # 3 minutes timeout for setup
    
    while proc.poll() is None:  # While process is still running
        # Check for timeout
        if time.time() - start_time > timeout:
            proc.terminate()  # Kill the script if it takes too long
            print("\n[!] Setup Timed Out!")
            return False, {"status": "error", "message": f"Setup exceeded {timeout}s timeout"}

        # Print dots one by one (max 3, then reset for visual effect)
        sys.stdout.write(".")
        sys.stdout.flush()
        dot_count += 1
        
        if dot_count % 3 == 0:
            # Simple backspace logic to clear dots and reset
            sys.stdout.write("\b\b\b   \b\b\b")
            sys.stdout.flush()
            
        time.sleep(1)

    print(" [Done]")  # Finalize the line upon completion

    # 4. Handle process results
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        return False, {
            "status": "error", 
            "message": "Infrastructure script failed", 
            "stderr": stderr
        }

    # 5. Collect real-time state instead of returning an empty list
    container_table = collect_container_table()
    
    # 6. Standardized response for api_server.py 
    try:
        container_table = collect_container_table()
        return True, {"status": "success", "containers": container_table}
    except Exception as e:
        return False, {"status": "error", "message": f"Setup succeeded but state collection failed: {str(e)}"}
    



def ns_ipsec_load(ns, vici_socket=None):
    """
    Loads strongSwan/swanctl configuration on a target Docker container.
    Delegates to 'swanctl --load-all' inside the container context.
    Follows the (bool, dict) return pattern for api_server.py consistency.
    """
    # 1. Define the load command
    # By default, we use --load-all to refresh connections, pools, and secrets.
    cmd = "swanctl --load-all"
    
    # 2. Handle optional VICI socket URI
    # In Docker, this usually defaults to unix:///var/run/charon.vici
    if vici_socket:
        uri = vici_socket if vici_socket.startswith("unix://") else f"unix://{vici_socket}"
        cmd += f" --uri {uri}"
    
    try:
        # 3. Execute via docker_exec helper 
        result = docker_exec(ns, cmd)
        
        # 4. Standardized Return
        success = (result["returncode"] == 0)
        return success, {
            "status": "success" if success else "error",
            "message": f"IPsec configuration loaded in container {ns}" if success else "Load failed",
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "rc": result["returncode"]
        }
    except Exception as e:
        return False, {
            "status": "error",
            "message": f"Execution error during config load: {str(e)}"
        }


def add_ns_ip(ns, ip_addr, interface):
    """Adds an IP to a container interface using docker exec"""
    result = docker_exec(ns, f"ip addr add {ip_addr} dev {interface}")
    
    if result["returncode"] == 0:
        return True, {"status": "success", "message": f"Added {ip_addr} to {ns}"}
    elif "File exists" in result["stderr"]:
        return True, {"status": "already_exists", "message": f"IP already present in {ns}"}
    return False, {"status": "error", "message": result["stderr"]}

def update_ns_swanctl(ns, new_params, vici_socket=None):
    """
    Updates strongSwan config in a container.
    Logic: Write to a temp file, docker cp it, then reload 
    """
    if ns not in CONFIG_STATE:
        return False, {"status": "error", "message": f"Container {ns} not initialized in CONFIG_STATE"}

    # 1. Retrieve the 'Existing' info for this host
    current_config = CONFIG_STATE[ns]

    # 2. Append NEW children if provided 
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
    
    # 5. Apply the configuration 
    conf_path = f"/etc/ipsec-ns/{ns}/swanctl/swanctl.conf"
    try:
        with open("/tmp/temp_swanctl.conf", "w") as f:
            f.write(config_text)
        #run_cmd(f"cp /tmp/temp_swanctl.conf {conf_path}")
        temp_path = "/tmp/temp_swanctl.conf"

        cp_res = run_cmd(f"docker cp {temp_path} {ns}:/etc/swanctl/swanctl.conf")           
        if cp_res["returncode"] != 0:
            return False, {"status": "error", "message": "Failed to copy config to container"}
        else:
            # Reload using docker exec
            uri = vici_socket if vici_socket.startswith("unix://") else f"unix://{vici_socket}"
            load_res = docker_exec(ns, f"swanctl --load-all --uri {uri}")
            if load_res["returncode"] != 0:
                return False, {"status": "error", "message": "Failed to get stats", "stderr": load_res["stderr"]}
            else:
                return True, {"status": "success", "message": "Configuration updated and loaded successfully"}
    except Exception as e:
        return False, {"status": "error", "message": f"Failed to copy config and update to container: {str(e)}"}
    
    

def get_ns_stats(ns, format_type="table", vici_socket=None):
    """Retrieves IPsec SA stats from a container via VICI """
    # Docker containers usually have standard VICI paths
    uri = vici_socket if vici_socket.startswith("unix://") else f"unix://{vici_socket}"

    result = docker_exec(ns, f"swanctl --list-sas --uri {uri}")
    if result["returncode"] != 0:
        return False, {"status": "error", "message": "Failed to get stats", "stderr": result["stderr"]}
    
    # Reuse the same parser logic as the NS driver
    return True, {"status": "success", "data": result["stdout"]}

def add_ns_child(ns, ike, child_name, vici_socket=None):
    """Initiates a Child SA inside a container """
    uri = vici_socket if vici_socket.startswith("unix://") else f"unix://{vici_socket}"
      
    result = docker_exec(ns, f"swanctl --initiate --ike {ike} --child {child_name} --uri {uri}")

    return (result["returncode"] == 0, {
        "status": "success" if result["returncode"] == 0 else "error",
        "message": result["stdout"] if result["returncode"] == 0 else result["stderr"]
    })

def terminate_ns_child(ns, child_name, ike_name=None, vici_socket=None):
    """Terminates a Child SA inside a container """
    uri = vici_socket if vici_socket.startswith("unix://") else f"unix://{vici_socket}"
    cmd = f"swanctl --terminate --child {child_name} --uri {uri}"

    if ike_name:
        cmd += f" --ike {ike_name}"
    result = docker_exec(ns, cmd)
    return (result["returncode"] == 0, {"status": "success", "stdout": result["stdout"]})

# def run_ns_iperf_server(server_ns, bind_ip, port=5201, logfile=None, pidfile=None):
#     """Starts iperf3 server in background inside a container """
#     # -d runs the container command in the background
#     cmd = f"docker exec -d {server_ns} iperf3 -s -1 -B {bind_ip} -p {port} --logfile {logfile} --pidfile {pidfile}"
#     res = run_cmd(cmd)
#     return (res["returncode"] == 0, {"status": "success", "message": f"iperf3 server started in {server_ns}"})


# def run_ns_iperf_server(server_ns, bind_ip, port, logfile, pidfile):
#     """
#     Docker-equivalent to run_ns_iperf_server.
#     Starts an iperf3 server inside a specific container in the background.
#     """
#     # 1. Build the iperf3 server command
#     # -s: server mode, -B: bind to loopback IP, -p: port
#     # --daemon: iperf3's internal backgrounding mechanism
#     # --logfile/--pidfile: paths INSIDE the container 
#     server_cmd = [
#         "iperf3",
#         "-s",
#         "-B", bind_ip,
#         "-p", str(port),
#         "--daemon",
#         "--logfile", logfile,
#         "--pidfile", pidfile
#     ]

#     # 2. Construct the full 'docker exec' command string
#     # We use 'sudo' for Docker daemon access and 'docker exec' for isolation 
#     full_cmd = ["sudo", "docker", "exec", server_ns] + server_cmd

#     try:
#         # 3. Execute as a detached background process
#         # Mirroring the 'run_ns_bg' logic to prevent blocking the API 
#         proc = subprocess.Popen(
#             full_cmd,
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             start_new_session=True
#         )

#         # 4. Standardized Return for IPERF_SERVERS tracking 
#         return True, {
#             "status": "success",
#             "message": f"iperf3 server started in container {server_ns} on port {port}",
#             "pid": proc.pid # Return the PID of the execution wrapper
#         }

#     except Exception as e:
#         return False, {
#             "status": "error",
#             "message": f"Failed to start Docker iperf server: {str(e)}"
#         }

def run_ns_iperf_server(server_ns, bind_ip, port, logfile, pidfile):
    """
    Improved Docker-equivalent for iperf3 server.
    Ensures log/pid paths are valid inside the container's mounted volumes.
    """
    # 1. Strip the host path and use the mounted container path (/var/log)
    # This assumes your Docker setup mounts './logs/{ns}:/var/log' [3]
    container_log = f"/var/log/{os.path.basename(logfile)}"
    container_pid = f"/var/log/{os.path.basename(pidfile)}"

    # 2. Build the command
    # We remove --daemon and use 'docker exec -d' for more reliable backgrounding
    server_cmd = [
        "iperf3",
        "-s",
        "-B", bind_ip,
        "-p", str(port),
        "--logfile", container_log,
        "--pidfile", container_pid
    ]

    # 3. Execute in detached mode (-d)
    # This ensures the process is managed by the Docker engine [4]
    full_cmd = ["sudo", "docker", "exec", "-d", server_ns] + server_cmd

    try:
        # We use run_cmd because docker exec -d returns immediately
        result = run_cmd(" ".join(full_cmd))
        
        if result["returncode"] == 0:
            return True, {
                "status": "success",
                "message": f"iperf3 server started in container {server_ns} (Detached)",
                "container_log": container_log
            }
        else:
            return False, result
    except Exception as e:
        return False, {"status": "error", "message": str(e)}


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

# def run_ns_iperf_client(ns, server_ip, protocol, port=5201, bandwidth=None, duration=5, logfile=None):
#     """
#     Runs an iperf3 client inside a Docker container and returns structured results.
#     Equivalent to the namespace version in test_api_lib_ns.py.
#     """
#     # 1. Build the base iperf3 command
#     # -c: client mode
#     # -p: target port (default 5201)
#     # -t: test duration in seconds (default 5)
#     # -J: output results in JSON format for the API to parse 
#     cmd = f"iperf3 -c {server_ip} -p {port} -t {duration} -J"

#     # 2. Add protocol-specific flags
#     if protocol.lower() == 'udp':
#         cmd += " -u"
#         if bandwidth:
#             # -b: bandwidth limit (e.g., '10M')
#             cmd += f" -b {bandwidth}"

#     # 3. Handle logging (Optional)
#     if logfile:
#         cmd += f" --logfile {logfile}"

#     try:
#         # 4. Execute inside the container via 'docker exec' 
#         # 'ns' in this context refers to the Container Name (e.g., 'hostA')
#         result = docker_exec(ns, cmd)
        
#         # 5. Standardized Return for api_server.py
#         success = (result["returncode"] == 0)
        
#         # Attempt to parse the JSON output from iperf3
#         try:
#             perf_data = json.loads(result["stdout"]) if success else None
#         except json.JSONDecodeError:
#             perf_data = {"raw_output": result["stdout"]}

#         return success, {
#             "status": "success" if success else "error",
#             "message": "Traffic test completed" if success else "Traffic test failed",
#             "results": perf_data,
#             "stderr": result["stderr"]
#         }

#     except Exception as e:
#         return False, {
#             "status": "error", 
#             "message": f"Execution error during iperf client run: {str(e)}"
#         }


def run_ns_iperf_client(ns, server_ip, protocol, port=5201, bandwidth=None, duration=5, logfile=None):
    """
    Runs an iperf3 client inside a Docker container.
    Captures JSON output for the API response.
    """
    # 1. Path Translation for Logging 
    # If a host-side log path is provided, convert it to the container's mounted /var/log
    container_logfile = None
    if logfile:
        container_logfile = f"/var/log/{os.path.basename(logfile)}"

    # 2. Build the iperf3 command
    # -c: client mode, -p: port, -t: duration, -J: JSON output
    cmd = ["iperf3", "-c", server_ip, "-p", str(port), "-t", str(duration), "-J"]

    # 3. Protocol and Bandwidth Handling 
    if protocol.lower() == "udp":
        cmd.append("-u")
        if bandwidth:
            cmd.extend(["-b", str(bandwidth)])
            
    if container_logfile:
        cmd.extend(["--logfile", container_logfile])

    # 4. Wrap in Docker Exec
    # 'ns' is the container name (e.g., 'hostA') 
    full_cmd = ["sudo", "docker", "exec", ns] + cmd

    try:
        # 5. Execute and capture output
        # We use subprocess.run to wait for the test to complete and get the JSON results
        result = subprocess.run(full_cmd, capture_output=True, text=True)
        
        # 6. Parse JSON results 
        success = (result.returncode == 0)
        try:
            perf_data = json.loads(result.stdout) if success else None
        except json.JSONDecodeError:
            perf_data = {"raw_output": result.stdout}

        return success, {
            "status": "success" if success else "error",
            "message": "Traffic test completed" if success else "Traffic test failed",
            "results": perf_data,
            "stderr": result.stderr
        }

    except Exception as e:
        return False, {"status": "error", "message": f"Client execution failed: {str(e)}"}

def check_ns_loopback_ping(src_ns, src_loopback, dst_loopback, count=4):
    """
    Pings between container loopback interfaces.
    """
    cmd = f"ping -I {src_loopback} -c {count} -W 2 {dst_loopback}"
    result = docker_exec(src_ns, cmd)
    
    success = (result["returncode"] == 0)
    return success, {
        "status": "success" if success else "error",
        "message": "Ping successful" if success else "Ping failed",
        "stdout": result["stdout"],
        "stderr": result["stderr"]
    }


def ns_cleanup():
    """
    Docker-specific cleanup equivalent to namespace mode teardown.
    Triggers 'ipsec_docker_cleanup.sh' to stop and remove all containers.
    """
    # 1. Locate the cleanup script using HOST_PATH
    script_path = f"{HOST_PATH}/ipsec_docker_clean.sh"
    
    if not os.path.isfile(script_path):
        return False, {"status": "error", "message": f"Cleanup script not found at {script_path}"}

    try:
        # 2. Execute the script via the run_cmd helper
        # run_cmd handles the sudo context required for Docker operations
        result = run_cmd(f"bash {script_path}")
        
        # 3. Standardized Return for api_server.py
        success = (result["returncode"] == 0)
        return success, {
            "status": "success" if success else "error",
            "message": "Docker infrastructure cleaned up" if success else "Cleanup failed",
            "stdout": result["stdout"],
            "stderr": result["stderr"]
        }
    except Exception as e:
        return False, {"status": "error", "message": f"Execution error during cleanup: {str(e)}"}