
import pytest
from test_lib.api import post

@pytest.fixture(scope="session")
def setup_ipsec():
    # Idempotent setup endpoint
    resp = post("/api/ipsec/setup", {})
    yield resp