"""Exercise runtime failures with real, bounded local subprocesses."""

import fcntl
import json
import os
import signal
import subprocess
import sys
import time

import pytest
from typer.testing import CliRunner

from insomnia_run.main import app
from insomnia_run.runner import InsoConfigurationError, InsoRunner


@pytest.fixture
def fake_inso(tmp_path, monkeypatch):
    binary = tmp_path / "inso"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "if sys.argv[1:] == ['run', 'collection', '--help']:\n"
        "    print('Usage: inso run collection [options]\\n  --reporter <reporter>')\n"
        "    sys.exit(0)\n"
        "os.write(1, bytes.fromhex(os.environ.get('FAKE_INSO_STDOUT', '')))\n"
        "os.write(2, bytes.fromhex(os.environ.get('FAKE_INSO_STDERR', '')))\n"
        "sys.exit(int(os.environ.get('FAKE_INSO_EXIT', '0')))\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")


@pytest.mark.parametrize("command", ["run-collection", "run-test"])
@pytest.mark.parametrize("stream", ["STDOUT", "STDERR"])
@pytest.mark.parametrize("include_raw", [False, True])
@pytest.mark.parametrize("has_tap", [False, True])
def test_cli_errors_keep_arbitrary_diagnostics_only_in_opt_in_raw_output(
    fake_inso, tmp_path, monkeypatch, command, stream, include_raw, has_tap
):
    secret = "PRIVATE_DIAGNOSTIC_SENTINEL"
    stdout = "1..1\nok 1 - passes\n" if has_tap else ""
    stderr = ""
    if stream == "STDOUT":
        stdout += f"Error: {secret}\n"
    else:
        stderr = f"Error: {secret}\n"
    monkeypatch.setenv("FAKE_INSO_STDOUT", stdout.encode().hex())
    monkeypatch.setenv("FAKE_INSO_STDERR", stderr.encode().hex())
    monkeypatch.setenv("FAKE_INSO_EXIT", "23")
    junit = tmp_path / "report.xml"
    args = [
        command,
        "-w",
        "fixture",
        "--output-format",
        "json",
        "--junit-output",
        str(junit),
    ]
    if include_raw:
        args.append("--include-raw-output")

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 3, result.output
    payload = json.loads(result.stderr)
    assert payload["run_error"]["kind"] in {"execution", "protocol"}
    assert payload["complete"] is False
    assert len(payload["results"]) == int(has_tap)
    assert all(r["status"] == "PASS" for r in payload["results"])
    assert all(secret not in r["description"] for r in payload["results"])
    assert secret not in payload["run_error"]["message"]
    assert (secret in result.stdout) is include_raw
    assert (secret in result.stderr) is include_raw
    assert ("raw_output" in payload) is include_raw
    assert secret not in junit.read_text(encoding="utf-8")


@pytest.mark.parametrize("command", ["run-collection", "run-test"])
def test_cli_reports_preserve_unicode_and_replace_invalid_bytes(
    fake_inso, monkeypatch, command
):
    monkeypatch.setenv("FAKE_INSO_STDOUT", b"1..1\nok 1 - caf\xc3\xa9 \xff\n".hex())

    result = CliRunner().invoke(
        app, [command, "-w", "fixture", "--output-format", "json"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stderr)["results"][0]["description"] == "caf\u00e9 \ufffd"
    assert "caf\u00e9 \ufffd" in result.stdout


@pytest.mark.parametrize("command", ["run-collection", "run-test"])
@pytest.mark.parametrize(
    "output",
    ["1..2\nok 1 - incomplete\n", "1..1\nok 1 - passes\nBail out! private\n"],
)
def test_successful_process_with_missing_or_incomplete_tap_fails_cli(
    fake_inso, monkeypatch, command, output
):
    monkeypatch.setenv("FAKE_INSO_STDOUT", output.encode().hex())

    result = CliRunner().invoke(
        app, [command, "-w", "fixture", "--output-format", "json"]
    )

    assert result.exit_code == 3, result.output
    payload = json.loads(result.stderr)
    assert payload["run_error"]["kind"] == "protocol"
    assert payload["complete"] is False
    assert [result["status"] for result in payload["results"]] == ["PASS"]


def test_successful_collection_without_assertions_has_a_neutral_empty_report(
    fake_inso, monkeypatch
):
    monkeypatch.setenv("FAKE_INSO_STDOUT", b"[network] Response succeeded\n".hex())

    result = CliRunner().invoke(
        app, ["run-collection", "-w", "fixture", "--output-format", "json"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stderr)["results"] == []
    assert "Passed" not in result.stdout
    assert "No assertions executed" in result.stdout


def test_test_suite_requires_tap_even_when_the_process_exits_successfully(fake_inso):
    result = CliRunner().invoke(
        app, ["run-test", "-w", "fixture", "--output-format", "json"]
    )

    assert result.exit_code == 3, result.output
    payload = json.loads(result.stderr)
    assert payload["results"] == []
    assert payload["run_error"]["kind"] == "protocol"
    assert payload["complete"] is False


def test_subprocess_replaces_invalid_utf8_without_losing_valid_unicode():
    result = InsoRunner._run_command(
        [
            sys.executable,
            "-c",
            "import os; os.write(1, b'caf\\xc3\\xa9 \\xff'); os.write(2, b'\\xfe')",
        ],
        5,
    )

    assert result.returncode == 0
    assert result.stdout == "caf\u00e9 \ufffd"
    assert result.stderr == "\ufffd"


def test_subprocess_decoding_does_not_depend_on_parent_locale():
    code = (
        "import sys; from insomnia_run.runner import InsoRunner; "
        "r = InsoRunner._run_command([sys.executable, '-c', "
        "\"import os; os.write(1, b'caf\\\\xc3\\\\xa9')\"], 5); "
        "assert r.stdout == 'caf\\u00e9', repr(r.stdout)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={
            **os.environ,
            "LC_ALL": "C",
            "PYTHONUTF8": "0",
            "PYTHONCOERCECLOCALE": "0",
        },
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("capability_probe", [False, True])
def test_timeout_stops_descendant_processes(tmp_path, monkeypatch, capability_probe):
    lock = tmp_path / "child.lock"
    ready = tmp_path / "child.ready"
    child = (
        "import fcntl, os, pathlib, sys, time; "
        "f = open(sys.argv[1], 'w'); fcntl.flock(f, fcntl.LOCK_EX); "
        "pathlib.Path(sys.argv[2]).write_text(str(os.getpid())); time.sleep(30)"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child!r}, sys.argv[1], sys.argv[2]]); "
        "time.sleep(30)"
    )
    if capability_probe:
        executable = tmp_path / "inso"
        executable.write_text(
            f"#!{sys.executable}\n"
            "import subprocess, sys, time\n"
            f"subprocess.Popen([sys.executable, '-c', {child!r}, {str(lock)!r}, {str(ready)!r}])\n"
            "time.sleep(30)\n"
        )
        executable.chmod(0o755)
        monkeypatch.setenv("PATH", str(tmp_path))
    runner = InsoRunner()
    try:
        if capability_probe:
            with pytest.raises(InsoConfigurationError, match="discovery timed out"):
                runner._supports_native_report()
        else:
            with pytest.raises(subprocess.TimeoutExpired):
                InsoRunner._run_command(
                    [sys.executable, "-c", parent, str(lock), str(ready)], 1
                )

        assert ready.exists(), "Descendant did not start before the timeout"
        with lock.open() as handle:
            deadline = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        pytest.fail("Descendant still holds its lock after timeout")
                    time.sleep(0.01)
    finally:
        if ready.exists():
            try:
                os.kill(int(ready.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
