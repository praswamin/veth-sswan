#!/usr/bin/env python3

from tabulate import tabulate
from test_api_lib import *
import subprocess
import time
import uuid
from datetime import datetime
from datetime import UTC



IPERF_SERVERS = {}

from flask import Flask, jsonify, request, Response

app = Flask(__name__)

HOST_PATH = os.environ['HOST_IPSEC_DIR']
print(f"HOST_PATH: {HOST_PATH}")


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

    #data = request.get_json(force=True)

    ns_a = "hostA"
    ns_b = "hostB"

    if_a = "vethA-hostA"
    if_b = "vethB-hostB"
    # ---- Collect current state ----
    try:
        rows = collect_veth_table()
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": "Failed to collect veth table",
            "details": str(e)
        }), 500

    # ---- Check if setup already exists ----
    if veth_setup_exists(rows, ns_a, ns_b, if_a, if_b):
        return jsonify({
            "status": "already_exists",
            "message": "Namespace and veth setup already present",
            "existing_entries": rows
        }), 200

    # ---- Otherwise create namespaces + veth ----

    script_path = f"{HOST_PATH}/ipsec_ns_setup.sh"

    # Run setup script
    setup_result = run_cmd(f"{script_path}")
    #setup_result = run_cmd(f"sudo {script_path}")
    #print(request.args.get("format", "table"))

    if setup_result["returncode"] != 0:
        return jsonify({
            "status": "failed",
            "script": setup_result
        }), 500

    # Collect veth info
    veth_table = collect_veth_table()

    # Format response
    as_table = request.args.get("format", "table") == "table"

    if as_table:
        table_str = tabulate(
            veth_table,
            headers=["Namespace", "Interface", "State", "IPv4 Address", "IPv6 Address"],
            tablefmt="grid"
        )
        #return Response(
        #    f"IPsec Namespace Setup Successful\n\n{table_str}\n",
        #    mimetype="text/plain"
        #)

        return jsonify({
                "status": status,
                "setup_output": f"IPsec Namespace Setup Successful\n\n{table_str}\n",
                "stdout": setup_result["stdout"],
                "stderr": setup_result["stderr"]
        })

    return jsonify({
        "status": "success",
        "setup_output": setup_result["stdout"],
        "veths": [
            dict(ns=row[0], ifname=row[1], state=row[2], ipv4=row[4], ipv6=row[5])
            for row in veth_table
        ]
    })

@app.route("/api/ipsec/cleanup", methods=["POST"])
def ipsec_cleanup():
    script_path = f"{HOST_PATH}/ipsec_ns_cleanup.sh"

    #  Run cleanup script
    cleanup_result = run_cmd(f"{script_path}")
    

    if cleanup_result["returncode"] != 0:
        return jsonify({
            "status": "failed",
            "script": cleanup_result
        }), 500
        
    return jsonify({
        "status": "success",
        "cleanup_output": cleanup_result["stdout"],
    })

@app.route("/api/ipsec/get_veth_if", methods=["GET"])
def ipsec_get_veth_if():
    get_ns = request.args.get("ns")

    veth_table = collect_veth_table()
    if veth_table is None:
        return jsonify({"error": "failed to collect veth info"}), 500
    else:
        formatted = format_veth_rows(veth_table, get_ns)

        if get_ns and not formatted:
            return jsonify({
                "status": "not_found",
                "message": f"No entries found for namespace '{get_ns}'"
            }), 404

        return jsonify({
            "status": "success",
            "count": len(formatted),
            "entries": formatted
        }), 200

@app.route("/api/ipsec/init_host", methods=["POST"])
def init_host():
    #ns = request.args.get("ns")  # hostA / hostB

    data = request.get_json(force=True)

    ns = data.get("ns")   # hostA / hostB
    if not ns:
        return jsonify({"error": "ns is required"}), 400
    
    script_path = f"{HOST_PATH}/ipsec-ns"

    #hosts = ["hostA", "hostB"]

    script = f"{script_path}/{ns}/init-{ns}.sh"
    #for host in hosts:
    #    script = f"{script_path}/{host}/init-{host}.sh"
    #    print(script)
    setup_result = run_in_ns(ns, script)

    status = "success" if setup_result["rc"] == 0 else "failure"

    return jsonify({
        "namespace": ns,
        "status": status,
        "return_code": setup_result["rc"],
        "stdout": setup_result["stdout"],
        "stderr": setup_result["stderr"]
    })


@app.route("/api/ipsec/load", methods=["POST"])
def swanctl_load():
    #ns = request.args.get("ns")

    data = request.get_json(force=True)

    ns = data.get("ns")   # hostA / hostB
    if not ns:
        return jsonify({"error": "ns is required"}), 400

    vici_socket = f"/etc/ipsec.d/run/charon-{ns}.vici"

    if not ns:
        return jsonify({"error": "ns is required"}), 400

    #out, err, rc = run_ns(ns, ["swanctl", "--load-all"])
    load_all, err, rc = run_swanctl_in_ns(ns, "--load-all", vici_socket)

    loaded, failed = [], []

    for line in load_all.splitlines():
        l = line.lower()
        if "loaded" in l:
            loaded.append(line.strip())
        if "failed" in l or "error" in l:
            failed.append(line.strip())

    status = "success" if rc == 0 and not failed else "partial-failure"

    return jsonify({
        "namespace": ns,
        "status": status,
        "loaded": loaded,
        "failed": failed,
        "stderr": err.strip() if err else None
    })


@app.route("/api/ipsec/stats", methods=["GET"])
def ipsec_stats():
    data = request.get_json(force=True)

    ns = data.get("ns")   # hostA / hostB
    fmt = request.args.get("format", "json").lower()  # json or table
    
    if not ns:
        return jsonify({"error": "ns parameter required"}), 400

    vici_socket = f"/etc/ipsec.d/run/charon-{ns}.vici"

    try:
        sa_stats, err, rc = run_swanctl_in_ns(ns, "--list-sas", vici_socket)
        
        status = "success" if rc == 0 and not err else "partial-failure"

        parsed = parse_vici(sa_stats)
        
        if fmt == "table":
            table = sas_to_table(parsed)
            headers = [
            "IKE SA",
            "IKE State",
            "Child SA",
            "Child State",
            "Proto",
            "Mode",
            "SPI-IN",
            "SPI-OUT",
            "Pkts-IN",
            "Pkts-OUT",
            "Bytes-IN",
            "Bytes-OUT",
            "Local TS",
            "Remote TS",
            "Local Host",
            "Remote Host",
            "Init SPI",
            "Resp SPI"
            ]

            
            return Response(
                tabulate(table, headers=headers, tablefmt="grid"),
                mimetype="text/plain"
            )
            return jsonify({
                "status": status,
                "table": tabulate(table, headers=headers, tablefmt="grid"),                              
                "namespace": ns
                               
            })

        # return jsonify(summary)
        return jsonify({
            "status": status,
            "namespace": ns,
            "parsed": parsed,  
            "raw": sa_stats.strip(),
            "stderr": err.strip() if err else None
        })   
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500




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
    

    # Step 1: initiate CHILD SA dynamically
    result = run_swanctl(ns, [
        "--initiate",
        "--ike", ike,
        "--child", child,
        "--timeout", "5"
    ])

    if result.returncode != 0:
        return jsonify({
            "status": "failed",
            "stderr": result.stderr.strip()
        }), 500

    return jsonify({
        "status": "success",
        "ike": ike,
        "child": child,
        "output": result.stdout.strip()
    })

from flask import request, jsonify

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

    cmd = ["iperf3", "-c", server_ip, "-t", str(duration), "-p", str(port)]

    if protocol == "udp":
        cmd += ["-u"]
        if bandwidth:
            cmd += ["-b", bandwidth]
    elif protocol == "sctp":
        cmd += ["--sctp"]

    #logfile = f"/var/log/iperf-{ns}.log"


    #ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    logfile = (
        f"{IPERF_LOG_DIR}iperf-client-"
        f"{ns}-{server_ip}-{protocol}-{ts}.log"
    )
    pid = run_ns_bg(ns, cmd, logfile)

    return jsonify({
        "namespace": ns,
        "tool": "iperf",
        "protocol": protocol,
        "server": server_ip,
        "pid": pid,
        "log": logfile,
        "status": "started"
    })



@app.route("/api/traffic/iperf/server", methods=["POST"])
def start_iperf_server():
    data = request.get_json(force=True)

    ns = data.get("ns")
    bind_ip = data.get("bind_ip")
    protocol = data.get("protocol", "tcp")
    port = int(data.get("port", 0)) or get_free_port()

    if not ns or not bind_ip:
        return jsonify({"error": "ns and bind_ip required"}), 400


    logfile = f"{IPERF_LOG_DIR}iperf-server-{ns}-{port}.log"
    pidfile = f"{IPERF_LOG_DIR}iperf-server-{ns}-{port}.pid"

    cmd = [
        "iperf3",
        "-s",
        "-B", bind_ip,
        "-p", str(port),
        "--daemon",
        "--logfile", logfile,
        "--pidfile", pidfile
    ]
        
    pid = run_ns_bg(ns, cmd, logfile)

    # simple sanity delay
    time.sleep(0.5)

    server_id = str(uuid.uuid4())

    IPERF_SERVERS[server_id] = {
        "ns": ns,
        "bind_ip": bind_ip,
        "port": port,
        "pid": pid
    }

    return jsonify({
        "server_id": server_id,
        "namespace": ns,
        "server_ip": bind_ip,
        "port": port,
        "protocol": protocol,
        "pid": pid,
        "status": "listening"
    })

@app.route("/api/traffic/iperf/servers", methods=["GET"])
def list_iperf_servers():
    return jsonify(IPERF_SERVERS)


@app.route("/api/traffic/gtpu", methods=["POST"])
def start_gtpu():
    data = request.get_json(force=True)

    ns = data.get("ns")
    local_ip = data.get("local_ip")
    remote_ip = data.get("remote_ip")
    direction = data.get("direction", "uplink")
    payload_size = int(data.get("payload_size", 256))
    teid_file = data.get("teid_file", f"{HOST_PATH}/traffic/hostA_hostB/lo_in_A_lo_in_B.json")
    count = int(data.get("count", 100))

    if not ns or not local_ip or not remote_ip:
        return jsonify({"error": "ns, local_ip, remote_ip required"}), 400

    cmd = [
        "python3",
        f"{HOST_PATH}/traffic/new_gtp_udp_send.py",
        "--local-ip", local_ip,
        "--remote-ip", remote_ip,
        "--teid-file", teid_file,
        "--direction", direction,
        "--payload-size", str(payload_size)
       ]

    #logfile = f"{GTPU_LOG_DIR}/gtpu-{ns}.log"
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")

    logfile = (
        f"{GTPU_LOG_DIR}gtpu-client-"
        f"{ns}-{local_ip}-{remote_ip}-{ts}.log"
    )

    pid = run_ns_bg(ns, cmd, logfile)

    return jsonify({
        "namespace": ns,
        "tool": "gtpu",
        "direction": direction,
        "pid": pid,
        "log": logfile,
        "status": "started"
    })


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

    cmd = [
        "--terminate",
        "--child", child
      ]

    if ike:
        cmd.extend(["--ike", ike])


    result = run_swanctl(ns, cmd)

    if result.returncode != 0:
        return jsonify({
            "status": "failed",
            "stderr": result.stderr.strip(),
            "stdout": result.stdout.strip()
        }), 500

    return jsonify({
        "status": "success",
        "namespace": ns,
        "child": child,
        "ike": ike,
        "output": result.stdout.strip()
    })

import os
import re
from flask import request, jsonify

IPERF_LOG_DIR = f"{HOST_PATH}/api_server/ipsec_api_server/iperf_logs/"
GTPU_LOG_DIR = f"{HOST_PATH}/api_server/ipsec_api_server/gtpu_logs/"
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

from flask import send_file

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
    #run_id = data.get("run_id")

    #if not run_id:
    #    return jsonify({"error": "run_id required"}), 400

    #entry = TRAFFIC_CLIENTS.get(run_id)
    #if not entry:
    #    return jsonify({"error": "run_id not found"}), 404

    #if entry["type"] != "gtpu":
    #    return jsonify({"error": "run_id is not gtpu"}), 400
    cmd = f"kill -SIGINT {pid}"
    print(f"cmd: {cmd}")


    run_in_ns(ns, cmd)

    #sigint_ns_process(ns, pid)

    #TRAFFIC_CLIENTS.pop(run_id, None)

    return jsonify({
        "status": "stopped",
        "signal": "SIGINT"
    })



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
