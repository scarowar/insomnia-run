import socket
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from insomnia_run.publication import ApiResponse, _https_transport


def test_publication_uses_https_proxy_without_exposing_token_in_connect(monkeypatch):
    received = []

    class RejectingProxy(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(1)
            request = b""
            while b"\r\n\r\n" not in request and len(request) < 8192:
                chunk = self.request.recv(8192 - len(request))
                if not chunk:
                    break
                request += chunk
            received.append(request)
            self.request.sendall(
                b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            )

    original_getaddrinfo = socket.getaddrinfo

    def local_proxy_dns_only(host, *args, **kwargs):
        if host == "api.example.invalid":
            raise socket.gaierror(socket.EAI_NONAME, "Direct target DNS is unavailable")
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_proxy_dns_only)
    for key in ("https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")

    with socketserver.TCPServer(("127.0.0.1", 0), RejectingProxy) as proxy:
        proxy.timeout = 1
        monkeypatch.setenv("HTTPS_PROXY", f"http://127.0.0.1:{proxy.server_address[1]}")
        worker = threading.Thread(target=proxy.handle_request, daemon=True)
        worker.start()
        try:
            with pytest.raises(OSError):
                _https_transport(
                    "GET",
                    "https://api.example.invalid/user",
                    {"Authorization": "Bearer private-publication-token"},
                    None,
                )
        finally:
            worker.join(timeout=3)

    assert not worker.is_alive()
    assert len(received) == 1, "Publication bypassed the configured HTTPS_PROXY"
    assert received[0].startswith(b"CONNECT api.example.invalid:443 HTTP/1.")
    assert b"private-publication-token" not in received[0]
    assert b"authorization:" not in received[0].lower()


def test_publication_does_not_follow_redirects_with_authorization(monkeypatch):
    paths = []

    class RedirectingApi(BaseHTTPRequestHandler):
        def do_GET(self):
            paths.append(self.path)
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/next")
                payload = b""
            else:
                self.send_response(200)
                payload = b"{}"
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    for key in (
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setenv("no_proxy", "127.0.0.1")

    with HTTPServer(("127.0.0.1", 0), RedirectingApi) as server:
        worker = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        worker.start()
        try:
            result = _https_transport(
                "GET",
                f"http://127.0.0.1:{server.server_address[1]}/start",
                {"Authorization": "Bearer synthetic-publication-token"},
                None,
            )
        finally:
            server.shutdown()
            worker.join(timeout=3)

    assert not worker.is_alive()
    assert result == ApiResponse(302, None)
    assert paths == ["/start"]
