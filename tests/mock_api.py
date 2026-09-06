"""Tiny local HTTP API used by the e2e workflow and the test fixtures.

Serves a fixed JSON surface on 127.0.0.1 so e2e runs never touch external
services (jsonplaceholder.typicode.com / httpbin.org).

Usage:
    python3 tests/mock_api.py --port 8081
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

ROUTES: dict[str, tuple[int, Any]] = {
    "/todos/1": (200, {"id": 1, "title": "delectus aut autem", "completed": False}),
    "/todos/404": (404, {"error": "todo not found"}),
    "/todos": (
        200,
        [
            {"id": 1, "title": "delectus aut autem", "completed": False},
            {"id": 2, "title": "quis ut nam facilis", "completed": False},
        ],
    ),
    "/users/1": (
        200,
        {"id": 1, "name": "Leanne Graham", "email": "leanne@apitest.example"},
    ),
}


class MockAPIHandler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict[str, Any] | list[Any]) -> None:
        body = (json.dumps(payload) + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/headers":
            self._send(200, {"headers": dict(self.headers.items())})
        elif path in ROUTES:
            status, payload = ROUTES[path]
            self._send(status, payload)
        else:
            self._send(404, {"error": f"no route for {path}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Local mock API for e2e tests")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    server = HTTPServer(("127.0.0.1", args.port), MockAPIHandler)
    print(f"Mock API listening on http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
