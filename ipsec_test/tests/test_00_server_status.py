from test_lib.api import get

def test_api_health():
    resp = get("/")
    assert resp["status"] == "success"