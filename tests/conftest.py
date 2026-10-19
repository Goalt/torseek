import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from torrseek.api.mock import MockClient  # noqa: E402


@pytest.fixture(scope="session")
def http_server():
    import mock_server

    srv = mock_server.start(MockClient(delay=(0, 0)), token="secret-token")
    yield srv
    srv.shutdown()


# To check a new adapter, add its name here and a branch below.
ADAPTERS = ["mock", "http"]


@pytest.fixture(params=ADAPTERS)
def client(request):
    if request.param == "mock":
        return MockClient(delay=(0, 0))
    if request.param == "http":
        from torrseek.api.http import HttpClient

        srv = request.getfixturevalue("http_server")
        return HttpClient(f"http://127.0.0.1:{srv.server_port}", "secret-token", timeout=5)
    raise ValueError(request.param)
