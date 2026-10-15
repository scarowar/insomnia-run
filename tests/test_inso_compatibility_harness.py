"""Check compatibility-harness tool selection without running a real Inso."""

from http.server import ThreadingHTTPServer
import os
import subprocess
import sys

import pytest

import test_inso_compatibility as compatibility


runtime = compatibility.runtime


@pytest.fixture(scope="module", autouse=True)
def controlled_tools(tmp_path_factory):
    root = tmp_path_factory.mktemp("compatibility-tools")
    selected = root / "selected tools" / "inso-13.3.1"
    competing = root / "competing" / "inso"
    for executable, message in (
        (selected, "selected binary"),
        (competing, "competing binary"),
    ):
        executable.parent.mkdir()
        executable.write_text(f"#!{sys.executable}\nprint({message!r})\n")
        executable.chmod(0o755)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(compatibility, "BINARY", str(selected))
        monkeypatch.setenv("HOME", str(root / "home"))
        monkeypatch.setenv("PATH", str(competing.parent))
        # This regression does not need the compatibility server's fixed port.
        monkeypatch.setattr(
            compatibility,
            "ThreadingHTTPServer",
            lambda address, handler: ThreadingHTTPServer((address[0], 0), handler),
        )
        yield str(competing.parent)


def test_runtime_uses_exact_binary_with_another_inso_on_path(controlled_tools, runtime):
    result = subprocess.run(
        ["inso", "--version"],
        env=runtime,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "selected binary"
    assert os.environ["PATH"] == controlled_tools
