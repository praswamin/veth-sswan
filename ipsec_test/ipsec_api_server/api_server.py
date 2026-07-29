#!/usr/bin/env python3

from unittest import result
from tabulate import tabulate
#from test_api_lib import *
import subprocess
import time
import uuid
from datetime import datetime
from datetime import UTC
import os
import re
#from flask import request, jsonify
from flask import Flask, jsonify, request, send_file



IPERF_SERVERS = {}


app = Flask(__name__)


HOST_PATH = os.environ['HOST_IPSEC_DIR']
print(f"HOST_PATH: {HOST_PATH}")

IPERF_LOG_DIR = f"{HOST_PATH}/ipsec_api_server/iperf_logs/"
GTPU_LOG_DIR = f"{HOST_PATH}/ipsec_api_server/gtpu_logs/"




IPERF_CLIENT_RE = re.compile(
    r"iperf-client-(?P<ns>[^-]+)-"
    r"(?P<ip>[^-]+)-"
    r"(?P<proto>[^-]+)-"
    r"(?P<ts>\d{8}-\d{6})\.log"
)

#GTPU_CLIENT_RE = re.compile(
#    r"gtpu-client-(?P<ns>[^-]+)-"
#    r"(?P<ip>[^-]+)-"
#    r"(?P<ip>[^-]+)-"
#    r"(?P<ts>\d{8}-\d{6})\.log"
#)


# 1. Identify the lab execution mode (defaults to 'ns' for Raspberry Pi namespaces)
MODE = os.environ.get('LAB_MODE', 'ns')

# 2. Setup the driver based on the configuration mode 
if MODE == 'ns':
    # Import the namespace-specific library as the active driver
    import test_api_lib_ns as driver
    print("API Server started in NAMESPACE mode")
elif MODE == 'docker':
    # Placeholder for the future Docker-specific library
    import test_api_lib_docker as driver 
    print("API Server started in DOCKER mode")
else:
    raise ValueError(f"Unsupported lab mode: {MODE}")




@app.route("/")
def home():
    #return "Hello, User! This is a IPsec test API server. Use the /api endpoints to interact with the IPsec test environment."
    return jsonify({
        "status": "success",
        "message": "Welcome to the IPsec test API server."
    }), 200


@app.route("/api/help")
def help_page():
    # Call the function to get all routes
    routes = get_all_routes()
    # You can return this as JSON
    return jsonify(routes)

def get_all_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        # Filter out rules that require parameters to avoid errors with url_for (optional)
        # or just get the rule string as shown in the alternative below
        
        # Alternative approach for simple URLs, just get the rule string and methods
        methods = ','.join(rule.methods)
        routes.append({'endpoint': rule.endpoint, 'methods': methods, 'rule': rule.rule})
    

    return routes


@app.route("/api/ipsec/setup", methods=["POST"])
def ipsec_setup():

    # Extract the 'format' argument from the request
    # Default is 'table' to maintain legacy behavior
    output_format = request.args.get("format", "table")
    
    # Pass the format to the driver's initialization function
    success, result = driver.init_setup(format_type=output_format)
    
    if not success:
        return jsonify(result), 500
        
    return jsonify(result)

@app.route('/namespace/add_ip', methods=['POST'])
def add_namespace_ip():
    """
    Endpoint to add an IP address to the loopback interface of a namespace.
    Matches the command: ip -n <ns> addr add <ip> dev lo 
    """
    data = request.json
    ns = data.get('ns')      # e.g., 'hostA'
    ip = data.get('ip')      # e.g., '10.10.0.2/32'
    interface = data.get('interface', 'lo')  # Default to loopback if not specified
    
    if not ns or not ip:
        return jsonify({"status": "error", "message": "Missing ns or ip"}), 400
   
    # This calls add_ns_ip() in test_api_lib_ns.py (or the Docker equivalent)
    success, result = driver.add_ns_ip(ns, ip, interface)

    # 3. Handle response based on driver success/failure
    if not success:
        return jsonify(result), 500
        
    return jsonify(result), 200
    


@app.route('/config/update_swanctl', methods=['POST'])
def update_swanctl():
    data = request.json
    ns = data.get('host')    # e.g., 'hostA'
    config = data.get('params', {})            
          
    # 1. Input Validation
    if not ns or not config:
        return jsonify({
            "status": "error", 
            "message": "Missing required fields: 'ns' and 'config' must be provided."
        }), 400

    # 2. 
    # This calls update_ns_swanctl in test_api_lib_ns.py (Namespace mode)
    try:
        # Standardized driver return: (bool success, dict result_data)
        vici_socket = f"/etc/ipsec.d/run/charon-{ns}.vici"
        success, result = driver.update_ns_swanctl(ns, config, vici_socket=vici_socket)
        
        status_code = 200 if success else 500
        return jsonify(result), status_code

    except AttributeError:
        # Graceful handling for future modes where the driver might not 
        # have implemented this function yet 
        return jsonify({
            "status": "error",
            "message": f"Update operation not implemented for current mode: {MODE}"
        }), 501
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Unexpected server error: {str(e)}"
        }), 500

    


@app.route("/api/ipsec/cleanup", methods=["POST"])
def ipsec_cleanup():

    # This calls update_ns_swanctl() in test_api_lib_ns.py (or the Docker equivalent)
    success, result = driver.ns_cleanup()

    #Handle response based on driver success/failure
    if not success:
        return jsonify(result), 500
        
    return jsonify(result), 200

@app.route("/api/ipsec/get_veth_if", methods=["GET"])
def ipsec_get_veth_if():
    get_ns = request.args.get("ns")

    # This calls get_ns_veth_info() in test_api_lib_ns.py (or the Docker equivalent)
    success, result = driver.get_ns_veth_info(get_ns, ifname=None)

    #Handle response based on driver success/failure
    if not success:
        return jsonify(result), 500
        
    return jsonify(result), 200

@app.route("/api/ipsec/init_host", methods=["POST"])
def init_host():
    #ns = request.args.get("ns")  # hostA / hostB

    data = request.get_json(force=True)

    ns = data.get("ns")   # hostA / hostB
    if not ns:
        return jsonify({"error": "ns is required"}), 400
    
    # This calls ns_init_host() in test_api_lib_ns.py (or the Docker equivalent)
    success, result = driver.ns_init_host(ns)

    #Handle response based on driver success/failure
    if not success:
        return jsonify(result), 500
        
    return jsonify(result), 200


@app.route("/api/ipsec/load", methods=["POST"])
def swanctl_load():
    #ns = request.args.get("ns")

    data = request.get_json(force=True)

    ns = data.get("ns")   # hostA / hostB
       
    # 1. Input Validation
    if not ns :
        return jsonify({
            "status": "error", 
            "message": "Missing required fields: 'ns' must be provided."
        }), 400

    # 2. 
    # This calls update_ns_swanctl in test_api_lib_ns.py (Namespace mode)
    # or will call a matching function in test_api_lib_docker.py later.
    try:
        # Standardized driver return: (bool success, dict result_data)
        vici_socket = f"/etc/ipsec.d/run/charon-{ns}.vici"
        success, result = driver.ns_ipsec_load(ns, vici_socket)
        
        status_code = 200 if success else 500
        return jsonify(result), status_code

    except AttributeError:
        # Graceful handling for future modes where the driver might not 
        # have implemented this function yet.
        return jsonify({
            "status": "error",
            "message": f"Update operation not implemented for current mode: {MODE}"
        }), 501
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Unexpected server error: {str(e)}"
        }), 500




@app.route("/api/ipsec/stats", methods=["GET"])
def ipsec_stats():
   # 1. Retrieve all parameters from the URL query string 
    ns = request.args.get("ns")
    fmt = request.args.get("format", "json").lower()
    
    # 2. Validate input
    if not ns:
        return jsonify({"status": "error", "message": "Missing required parameter: 'ns'"}), 400

    # 3. Sanitize the namespace string
    ns = ns.strip()

    # 4. Define the VICI socket (or let the driver handle it if vici_socket=None) 
    vici_socket = f"/etc/ipsec.d/run/charon-{ns}.vici"
            
    # 5. Delegate to the active driver (Namespace or Docker) 
    # We pass fmt to the format_type parameter of your driver function
    success, result = driver.get_ns_stats(ns, format_type=fmt, vici_socket=vici_socket)
        
    status_code = 200 if success else 500
    return jsonify(result), status_code




@app.route("/api/ipsec/child/add", methods=["POST"])
def add_child_sa():
    data = request.json or {}

    required = ["ns", "ike", "child"]
    
    for k in required:
        if k not in data:
            return jsonify({"error": f"missing field '{k}'"}), 400

    ns         = data["ns"]
    ike        = data["ike"]
    child      = data["child"]

    vici_socket = f"/etc/ipsec.d/run/charon-{ns}.vici"

    # 2. Driver Delegation
    # This calls the new function in test_api_lib_ns.py
    success, result = driver.add_ns_child(ns, ike, child, vici_socket=vici_socket)

    # 3. Response Handling
    status_code = 200 if success else 500
    return jsonify(result), status_code






@app.route("/api/traffic/iperf", methods=["POST"])
def start_iperf():
    data = request.get_json(force=True)

    ns = data.get("ns")
    server_ip = data.get("server_ip")
    protocol = data.get("protocol", "tcp")
    bandwidth = data.get("bandwidth")
    duration = int(data.get("duration", 10))
    port = int(data.get("port", 5201))

    if not ns or not server_ip:
        return jsonify({"error": "ns and server_ip required"}), 400

    #ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    logfile = (
        f"{IPERF_LOG_DIR}iperf-client-"
        f"{ns}-{server_ip}-{protocol}-{ts}.log"
    )
    

    success, result = driver.run_ns_iperf_client(ns, server_ip, protocol=protocol, port=port, duration=duration, bandwidth=bandwidth, logfile=logfile)
    return jsonify(result), 200 if success else 500



@app.route("/api/traffic/iperf/server", methods=["POST"])
def start_iperf_server():
    data = request.get_json(force=True)

    ns = data.get("ns")
    bind_ip = data.get("bind_ip")
    port = int(data.get("port", 0)) or driver.get_free_port()

    if not ns or not bind_ip:
        return jsonify({"error": "ns and bind_ip required"}), 400


    logfile = f"{IPERF_LOG_DIR}iperf-server-{ns}-{port}.log"
    pidfile = f"{IPERF_LOG_DIR}iperf-server-{ns}-{port}.pid"

    success, result = driver.run_ns_iperf_server(server_ns=ns, bind_ip=bind_ip, port=port, logfile=logfile, pidfile=pidfile)

    if success:
        # 4. ADD DETAILS TO IPERF_SERVERS
        # We use a composite key of namespace and port for unique tracking
        server_key = f"{ns}:{port}"
        pid = result.get("pid")
        
        IPERF_SERVERS[server_key] = {
            "ns": ns,
            "port": port,
            "bind_ip": bind_ip,
            "pid": pid,
            "logfile": logfile,
            "status": "LISTENING", # Initial assumption based on success
            "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return jsonify({
            "status": "success",
            "message": f"iperf3 server started in {ns} on port {port}",
            "details": IPERF_SERVERS[server_key]
        }), 200
    else:
        return jsonify(result), 500



    return jsonify(result), 200 if success else 500

   


@app.route("/api/traffic/iperf/servers", methods=["GET"])
def list_iperf_servers():
    """
    Returns a detailed list of all iperf3 servers with live runtime status.
    """
    status_report = {}
    
    # IPERF_SERVERS is the global dict tracking { "hostB:5201": { ... } } [3]
    for key, info in IPERF_SERVERS.items():
        ns = info.get('ns')
        port = info.get('port')
        
        # 1. Perform live verification via the driver
        is_running, live_status = driver.check_ns_iperf_status(ns, port)
        
        # 2. Enrich the response with the live detail
        status_report[key] = {
            "ns": ns,
            "port": port,
            "bind_ip": info.get('bind_ip'),
            "pid": info.get('pid'),
            "status": live_status, # <--- "LISTENING" or "STOPPED"
            "last_verified": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
    return jsonify(status_report)


@app.route("/api/traffic/gtpu", methods=["POST"])
def start_gtpu():
    data = request.get_json(force=True)

    ns = data.get("ns")
    local_ip = data.get("local_ip")
    remote_ip = data.get("remote_ip")
    direction = data.get("direction", "uplink")
    payload_size = int(data.get("payload_size", 256))
    teid_file = data.get("teid_file", f"{HOST_PATH}/traffic/hostA_hostB/lo_in_A_lo_in_B.json")
    #count = int(data.get("count", 100))

    if not ns or not local_ip or not remote_ip:
        return jsonify({"error": "ns, local_ip, remote_ip required"}), 400

    #logfile = f"{GTPU_LOG_DIR}/gtpu-{ns}.log"
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    logfile = (
        f"{GTPU_LOG_DIR}gtpu-client-"
        f"{ns}-{local_ip}-{remote_ip}-{ts}.log"
    )

    # Calls start_ns_gtpu_server in the driver
    success, result = driver.start_ns_gtpu_server(ns, local_ip, remote_ip, teid_file, direction, payload_size, logfile)
    return jsonify(result), 200 if success else 500



@app.route("/api/ipsec/child/terminate", methods=["POST"])
def terminate_child_sa():
    data = request.get_json(force=True)

    ns = data.get("ns")
    child = data.get("child")
    ike = data.get("ike")
    #socket = data.get("socket", "/etc/ipsec.d/run/charon.vici")

    if not ns or not child:
        return jsonify({
            "error": "ns and child are required"
        }), 400

    # This calls terminate_ns_child() in test_api_lib_ns.py (or the Docker equivalent)
    success, result = driver.terminate_ns_child(ns, child, ike)

    # 3. Handle response based on driver success/failure
    status_code = 200 if success else 500
    return jsonify(result), status_code

    


@app.route("/api/traffic/iperf/runs", methods=["GET"])
def list_iperf_runs():
    ns_filter = request.args.get("ns")
    ip_filter = request.args.get("server_ip")
    proto_filter = request.args.get("protocol")

    runs = []

    for fname in os.listdir(IPERF_LOG_DIR):
        m = IPERF_CLIENT_RE.match(fname)
        if not m:
            continue

        meta = m.groupdict()

        if ns_filter and meta["ns"] != ns_filter:
            continue
        if ip_filter and meta["ip"] != ip_filter:
            continue
        if proto_filter and meta["proto"] != proto_filter:
            continue

        runs.append({
            "file": fname,
            "namespace": meta["ns"],
            "server_ip": meta["ip"],
            "protocol": meta["proto"],
            "timestamp": meta["ts"]
        })

    return jsonify(sorted(runs, key=lambda x: x["timestamp"], reverse=True))



@app.route("/api/traffic/iperf/run/<path:filename>", methods=["GET"])
def get_iperf_run(filename):
    if not filename.startswith("iperf-client-"):
        return jsonify({"error": "invalid file"}), 400

    full_path = os.path.join(IPERF_LOG_DIR, filename)

    if not os.path.isfile(full_path):
        return jsonify({"error": "not found"}), 404

    return send_file(full_path, mimetype="text/plain")



@app.route("/api/traffic/gtpu/stop", methods=["POST"])
def stop_gtpu():
    data = request.get_json(force=True)
    ns = data.get("ns")
    pid = data.get("pid")
    print(f"ns: {ns}, pid: {pid}")
    # This calls terminate_ns_child() in test_api_lib_ns.py (or the Docker equivalent)
    success, result = driver.stop_ns_gtpu_server(ns, pid)

    # 3. Handle response based on driver success/failure
    status_code = 200 if success else 500
    return jsonify(result), status_code


@app.route('/api/traffic/ping_loopback', methods=['POST'])
def ping_loopback():
    """
    Endpoint to verify IPsec tunnel by pinging loopback IPs.
    Default: hostA (10.10.0.1) -> hostB (10.10.1.1)
    """
    data = request.json
    src_ns = data.get("src_ns", "hostA")
    src_ip = data.get("src_ip", "10.10.0.1")
    dst_ip = data.get("dst_ip", "10.10.1.1")
    count = data.get("count", 4)

    # Delegate to the active driver (NS or Docker) 
    success, result = driver.check_ns_loopback_ping(src_ns, src_ip, dst_ip, count)
    
    return jsonify(result), 200 if success else 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
