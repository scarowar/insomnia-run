"""Deterministic HTTP fixtures for the GitHub Actions end-to-end suite."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import urlsplit


class FixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlsplit(self.path).path
        if path == "/health":
            self._send_json(200, {"status": "ok"})
        elif path == "/todos/1":
            self._send_json(200, {"id": 1, "title": "local todo", "completed": False})
        elif path == "/todos":
            self._send_json(200, [{"id": 1, "title": "local todo"}])
        elif path == "/users/1":
            self._send_json(
                200,
                {"id": 1, "name": "Local User", "email": "local@example.test"},
            )
        elif path == "/headers":
            self._send_json(200, {"headers": dict(self.headers.items())})
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8765), FixtureHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
