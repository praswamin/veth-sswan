from test_lib.api import post

def test_child_add():
    resp = post("/api/ipsec/child/add", {"ns": "hostA", "ike": "net-test", "child": "net"})

    assert resp["status"] == "success"
    assert resp["child"] == "net"

    assert "output" in resp
    assert len(resp["output"]) > 0

    assert "CHILD_SA net" in resp["output"]
    assert "established" in resp["output"]

    assert "initiate completed successfully" in resp["output"]

    assert "initiate completed successfully" in resp["output"]
    

    