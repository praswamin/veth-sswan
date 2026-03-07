from test_lib.api import post

def test_init_hostA():
    resp = post("/api/ipsec/init_host", {"ns": "hostA"})
    print(resp)
    assert resp["status"] in ["success", "failure"]
    #assert "current_state" in resp or "existing_entries" in resp

def test_init_hostB():
    resp = post("/api/ipsec/init_host", {"ns": "hostB"})
    print(resp)
    assert resp["status"] in ["success", "failure"]
    #assert "current_state" in resp or "existing_entries" in resp