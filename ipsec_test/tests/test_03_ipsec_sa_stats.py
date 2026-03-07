from test_lib.api import get, post  

def test_sa_stats():
    resp = get("/api/ipsec/stats", {"ns": "hostA", "format": "table"})
    #resp = get("/api/ipsec/stats", {"ns": "hostA"})

    #assert "stats" in resp
    #assert isinstance(resp["stats"], dict)

    ike = resp["event"]["net-test"]

    # Validate IKE SA State and IDs
    assert ike["state"] == "ESTABLISHED"
    assert ike["local-id"] == "hostA"
    assert ike["remote-id"] == "hostB"

    child = ike["child-sas"]["net-1"]

    # Validate Child SA State and Protocol
    assert child["state"] == "INSTALLED"
    assert child["name"] == "net"
    assert child["protocol"] == "ESP"

    # Validate Child SA Mode
    assert child["mode"] == "TUNNEL"

    # Validate Child SA Encryption and Integrity Algorithms
    assert child["encr-alg"] == "AES_CBC"
    assert child["encr-keysize"] == "128"
    assert child["integ-alg"] == "HMAC_SHA2_256_128"

    # Validate SPI values
    assert child["spi-in"] is not None
    assert child["spi-out"] is not None
    assert int(child["spi-in"], 16) > 0
    assert int(child["spi-out"], 16) > 0


    # Validate Traffic Selectors
    assert child["local-ts"] == "10.10.0.0/28"
    assert child["remote-ts"] == "10.10.1.0/28"

    # Validate Packet Counters
    assert int(child["spi-in"], 16) >= 0
    assert int(child["spi-out"], 16) >= 0