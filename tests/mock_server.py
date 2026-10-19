"""A local HTTP server that speaks the assumed API on top of MockClient.

Used to run the same contract tests against HttpClient. Also handy by hand:
    python3 tests/mock_server.py 8080
    TORRSEEK_ADAPTER=http TORRSEEK_BASE_URL=http://127.0.0.1:8080 python3 -m torrseek
"""
from __future__ import annotations

import json
import sys
import threading
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from torrseek.api.base import ApiError, NetworkError, NotFound, RateLimited  # noqa: E402
from torrseek.api.mock import MockClient  # noqa: E402
from torrseek.models import Sort  # noqa: E402


def _default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o))


def make_handler(client: MockClient, token: str | None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep test output quiet
            pass

        def _send(self, code: int, body: bytes, ctype="application/json", headers=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj):
            self._send(200, json.dumps(obj, default=_default).encode())

        def do_GET(self):
            if token and self.headers.get("Authorization") != f"Bearer {token}":
                return self._send(401, b'{"error":"unauthorized"}')
            url = urlparse(self.path)
            parts = [unquote(p) for p in url.path.strip("/").split("/")]
            try:
                if parts == ["search"]:
                    qs = parse_qs(url.query)
                    page = client.search(qs.get("q", [""])[0], category=qs.get("cat", [None])[0],
                                         page=int(qs.get("page", ["1"])[0]),
                                         sort=Sort(qs.get("sort", ["seeders"])[0]))
                    return self._json(asdict(page))
                if len(parts) == 2 and parts[0] == "torrents":
                    return self._json(asdict(client.details(parts[1])))
                if len(parts) == 3 and parts[0] == "torrents" and parts[2] == "file":
                    return self._send(200, client.download_torrent(parts[1]), "application/x-bittorrent")
                return self._send(404, b'{"error":"no route"}')
            except NotFound:
                return self._send(404, b'{"error":"not found"}')
            except RateLimited as e:
                return self._send(429, b'{"error":"rate limited"}', headers={"Retry-After": f"{e.retry_after:g}"})
            except NetworkError:
                self.close_connection = True
                self.connection.close()  # simulate a dropped connection
            except ApiError:
                return self._send(500, b'{"error":"internal"}')

    return Handler


def start(client: MockClient | None = None, port: int = 0, token: str | None = None):
    client = client or MockClient(delay=(0, 0))
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(client, token))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":
    srv = start(MockClient(), int(sys.argv[1]) if len(sys.argv) > 1 else 8080)
    print(f"mock API on http://127.0.0.1:{srv.server_port}")
    threading.Event().wait()
