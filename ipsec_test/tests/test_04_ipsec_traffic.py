from test_lib.api import post
import time

def test_iperf_traffic():

    server = post("/api/traffic/iperf/server", {
        "ns": "hostB",
        "bind_ip": "10.10.1.1",
        "protocol": "udp"
    })

    assert "port" in server

    client = post("/api/traffic/iperf", {
        "ns": "hostA",
        "server_ip": "10.10.0.1",
        "protocol": "udp",
        "duration": 5
    })

    assert client["status"] == "started"

    time.sleep(6)