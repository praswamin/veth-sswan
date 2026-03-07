from test_lib.api import post

def test_namespace_setup(setup_ipsec):
    resp = post("/api/ipsec/setup", {})
    assert resp["status"] in ["created", "already_exists"], f"Expected ['created', 'already_exists'], but got {resp['status']}"
    #assert resp["status"] == "success"
     

    if resp["status"] == "created":
        assert "setup_output" in resp
        assert len(resp["setup_output"]) > 0

        # Validate response structure
        assert "veths" in resp

        # Validate veth pairs
        assert isinstance(resp["veths"], list)
        assert len(resp["veths"]) >= 2

        namespaces = [v["ns"] for v in resp["veths"]]
        assert "hostA" in namespaces
        assert "hostB" in namespaces
        assert "router" in namespaces

        interfaces = [v["ifname"] for v in resp["veths"]]

        assert "vethA" in interfaces
        assert "vethB" in interfaces

    
        for v in resp["veths"]:
            assert v["state"] == "UP"
    

        for v in resp["veths"]:
            assert v["ipv4"] is not None
            assert "10.200" in v["ipv4"]
    
        assert resp["setup_output"] is not None
        assert len(resp["setup_output"]) > 0

    if resp["status"] == "already_exists":
        assert "message" in resp
        assert resp["message"] == "Namespace and veth setup already present"
        #print(f"existing_entries = {resp['existing_entries']}")
        #for row in resp["existing_entries"]:
        #    print(dict(ns=row[0], ifname=row[1], state=row[2], ipv4=row[4], ipv6=row[5]))
        print("\nExisting namespace entries:")

        rows = resp['existing_entries']
        for row in rows:
            ns, ifname, state, ipv4, ipv6 = row
            print(f"{ns:6} {ifname:6} {state:4} {ipv4}")
        
        namespaces = [row[0] for row in rows]
        assert "hostA" in namespaces
        assert "hostB" in namespaces

        interfaces = [row[1] for row in rows]
        assert any('vethA' in iface for iface in interfaces)
        assert any('vethB' in iface for iface in interfaces)
        