"""Opt-in tests against an official Inso binary and the deterministic HTTP fixture.

Set INSOMNIA_RUN_INSO_BINARY to a verified Inso binary to run these tests.
"""

from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from threading import Thread
from xml.etree import ElementTree

import pytest


ROOT = Path(__file__).resolve().parents[1]
BINARY = os.environ.get("INSOMNIA_RUN_INSO_BINARY")
pytestmark = pytest.mark.skipif(
    not BINARY, reason="Set INSOMNIA_RUN_INSO_BINARY to a verified release"
)


@pytest.fixture(scope="module")
def runtime():
    binary = Path(BINARY).resolve()
    assert binary.is_file()
    (Path.home() / ".cache" / "pkg").mkdir(parents=True, exist_ok=True)
    handler = runpy.run_path(str(ROOT / "tests/fixtures/e2e_server.py"))[
        "FixtureHandler"
    ]
    server = ThreadingHTTPServer(("127.0.0.1", 8765), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {**os.environ, "PATH": f"{binary.parent}:{os.environ['PATH']}"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize(
    "command,fixture,identifier,count,failures",
    [
        ("run-collection", "passing_suite.yaml", None, 3, 0),
        ("run-test", "passing_test_suite.yaml", "Todo API Tests", 2, 0),
        ("run-collection", "mixed_results_suite.yaml", None, 3, 1),
        ("run-test", "mixed_test_suite.yaml", "Mixed Results Suite", 3, 1),
        ("run-collection", "env_var_test.yaml", None, 1, 0),
    ],
)
def test_real_inso_reports(
    runtime, tmp_path, command, fixture, identifier, count, failures
):
    junit = tmp_path / "junit.xml"
    args = [
        sys.executable,
        "-m",
        "insomnia_run.main",
        command,
        "-w",
        str(ROOT / "tests/fixtures" / fixture),
        "--env",
        "Test Environment",
        "--output-format",
        "json",
        "--junit-output",
        str(junit),
    ]
    if identifier:
        args.extend(["--identifier", identifier])
    if fixture == "env_var_test.yaml":
        args.extend(["--env-var", "API_TOKEN=test_secret_from_env_var"])

    result = subprocess.run(
        args, env=runtime, capture_output=True, text=True, timeout=90, check=False
    )

    assert result.returncode == int(failures > 0), result.stdout + result.stderr
    payload = json.loads(result.stderr)
    assert len(payload["results"]) == count
    assert payload["plan_end"] == count
    assert [item["id"] for item in payload["results"]] == list(range(1, count + 1))
    assert sum(item["status"] == "FAIL" for item in payload["results"]) == failures
    assert "raw_output" not in payload
    xml = ElementTree.parse(junit).getroot()
    assert xml.get("tests") == str(count)
    assert xml.get("failures") == str(failures)


def test_real_inso_missing_workspace_is_a_report_failure(runtime, tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "insomnia_run.main",
            "run-collection",
            "-w",
            str(tmp_path / "missing"),
            "--output-format",
            "json",
        ],
        env=runtime,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert payload["results"][0]["status"] == "FAIL"
    assert "Inso CLI Error" in payload["results"][0]["description"]


def test_real_inso_iterations_have_unique_ids(runtime):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "insomnia_run.main",
            "run-collection",
            "-w",
            str(ROOT / "tests/fixtures/passing_suite.yaml"),
            "--env",
            "Test Environment",
            "--iteration-count",
            "2",
            "--output-format",
            "json",
        ],
        env=runtime,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stderr)
    assert [item["id"] for item in payload["results"]] == [1, 2, 3, 4, 5, 6]
    assert payload["plan_end"] == 6


def test_runner_environment_is_not_an_implicit_insomnia_override(runtime):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "insomnia_run.main",
            "run-collection",
            "-w",
            str(ROOT / "tests/fixtures/env_var_test.yaml"),
            "--env",
            "Test Environment",
            "--output-format",
            "json",
        ],
        env={**runtime, "API_TOKEN": "test_secret_from_env_block"},
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stderr)
    assert len(payload["results"]) == 1
    assert payload["results"][0]["status"] == "FAIL"
