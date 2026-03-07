from test_lib.api import post

def test_load_hostA():
    resp = post("/api/ipsec/load", {"ns": "hostA"})
    assert resp["status"] in ["success", "partial-failure"]
    

def test_load_hostB():
    resp = post("/api/ipsec/load", {"ns": "hostB"})
    assert resp["status"] in ["success", "partial-failure"]
    