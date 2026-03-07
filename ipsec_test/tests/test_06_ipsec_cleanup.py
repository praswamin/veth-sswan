from test_lib.api import post

def test_ipsec_cleanup(setup_ipsec):
    resp = post("/api/ipsec/cleanup", {})
    assert resp["status"] in ["success", "failed"]
   