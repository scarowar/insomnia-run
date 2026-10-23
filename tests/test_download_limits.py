import io
from pathlib import Path
import sys
import time
import signal
from urllib.error import HTTPError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import install_runtime


class Response(io.BytesIO):
    def __init__(self, content=b"archive", *, status=200):
        super().__init__(content)
        self.status = status


@pytest.mark.parametrize("status", [201, 204, 206])
def test_only_http_200_can_write_archive_bytes(monkeypatch, status):
    class Opener:
        def open(self, request, timeout):
            return Response(status=status)

    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    output = io.BytesIO()

    with pytest.raises(ValueError, match="200|HTTP|status"):
        install_runtime._download_https(
            "https://github.com/archive", output, "", None, 1024
        )

    assert output.getvalue() == b""


def test_token_origin_must_be_permitted_before_any_network_request(monkeypatch):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            return Response()

    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    output = io.BytesIO()

    with pytest.raises(ValueError, match="origin"):
        install_runtime._download_https(
            "https://github.com/archive",
            output,
            "private-token",
            ("unlisted.example", 443),
            1024,
        )

    assert requests == []
    assert output.getvalue() == b""


def test_token_is_only_sent_to_its_permitted_origin(monkeypatch):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise HTTPError(
                    request.full_url,
                    302,
                    "Found",
                    {"Location": "https://api.github.com/archive"},
                    io.BytesIO(),
                )
            return Response()

    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    output = io.BytesIO()
    install_runtime._download_https(
        "https://github.com/archive",
        output,
        "private-token",
        ("api.github.com", 443),
        1024,
    )

    assert requests[0].get_header("Authorization") is None
    assert requests[1].get_header("Authorization") == "Bearer private-token"
    assert output.getvalue() == b"archive"


def test_request_authority_uses_canonical_permitted_origin(monkeypatch):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            return Response()

    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    output = io.BytesIO()
    install_runtime._download_https(
        "https://MiRrOr.ExAmPlE:8443/archive?signature=a%2Bb",
        output,
        "",
        None,
        1024,
        ("https://mirror.example:8443",),
    )

    assert requests == ["https://mirror.example:8443/archive?signature=a%2Bb"]
    assert output.getvalue() == b"archive"


def test_download_has_five_minute_total_deadline_across_chunks(monkeypatch):
    elapsed = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: elapsed[0])

    class SlowResponse(Response):
        def read(self, size=-1):
            elapsed[0] += 61
            return super().read(1)

        read1 = read

    class Opener:
        def open(self, request, timeout):
            return SlowResponse(b"abcdef")

    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    output = io.BytesIO()

    with pytest.raises(ValueError, match="deadline|timed out|time limit"):
        install_runtime._download_https(
            "https://github.com/archive", output, "", None, 1024
        )

    assert len(output.getvalue()) < 6


def test_redirects_and_response_chunks_share_one_total_deadline(monkeypatch):
    elapsed = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: elapsed[0])
    requests = []

    class SlowResponse(Response):
        def read(self, size=-1):
            elapsed[0] += 10
            return super().read(1)

        read1 = read

    class Opener:
        def open(self, request, timeout):
            elapsed[0] += 59
            requests.append(request)
            if len(requests) < 5:
                raise HTTPError(
                    request.full_url,
                    302,
                    "Found",
                    {"Location": f"https://github.com/archive-{len(requests)}"},
                    io.BytesIO(),
                )
            return SlowResponse(b"ab")

    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    output = io.BytesIO()

    with pytest.raises(ValueError, match="deadline|timed out|time limit"):
        install_runtime._download_https(
            "https://github.com/archive", output, "", None, 1024
        )

    assert len(output.getvalue()) < 2


@pytest.mark.parametrize("blocked_stage", ["open", "body"])
def test_total_deadline_interrupts_blocked_network_operations(
    monkeypatch, blocked_stage
):
    class StalledResponse(Response):
        def read1(self, size=-1):
            if blocked_stage == "body":
                time.sleep(2)
            return super().read1(size)

    class Opener:
        def open(self, request, timeout):
            if blocked_stage == "open":
                time.sleep(2)
            return StalledResponse()

    monkeypatch.setattr(install_runtime, "_DOWNLOAD_DEADLINE_SECONDS", 0.05)
    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    previous_handler = signal.getsignal(signal.SIGALRM)
    started = time.monotonic()
    output = io.BytesIO()
    with pytest.raises(ValueError, match="deadline|timed out|time limit"):
        install_runtime._download_https(
            "https://github.com/archive", output, "", None, 1024
        )
    assert time.monotonic() - started < 0.5
    assert signal.getsignal(signal.SIGALRM) == previous_handler
    assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


def test_download_restores_a_preexisting_alarm(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            return Response()

    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    original_handler = signal.getsignal(signal.SIGALRM)
    original_timer = signal.getitimer(signal.ITIMER_REAL)

    def caller_alarm(signum, frame):
        pytest.fail("Caller alarm unexpectedly fired")

    signal.signal(signal.SIGALRM, caller_alarm)
    signal.setitimer(signal.ITIMER_REAL, 10, 7)
    try:
        install_runtime._download_https(
            "https://github.com/archive", io.BytesIO(), "", None, 1024
        )
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        assert 0 < remaining <= 10
        assert interval == 7
        assert signal.getsignal(signal.SIGALRM) is caller_alarm
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, original_handler)
        signal.setitimer(signal.ITIMER_REAL, *original_timer)


@pytest.mark.parametrize(
    "query",
    [
        "next=https://127.0.0.1/private",
        "@127.0.0.1:8080/private",
        "//127.0.0.1/private",
        "signature=a%2Bb&host=evil.example",
        "%0d%0aHost:%20evil.example",
    ],
)
def test_query_content_cannot_replace_the_authorized_request_host(query):
    request = install_runtime._download_request(
        f"https://github.com/archive?{query}", {("github.com", 443)}, "", None
    )
    assert request.type == "https"
    assert request.host == "github.com"
    assert request.selector == f"/archive?{query}"
