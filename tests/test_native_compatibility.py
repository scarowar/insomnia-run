"""Opt-in behavioral regressions against a checksum-verified official Inso binary."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
import time
from xml.etree import ElementTree

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
BINARY = os.environ.get("INSOMNIA_RUN_INSO_BINARY")
pytestmark = pytest.mark.skipif(
    not BINARY, reason="Requires a verified official Inso binary"
)


@pytest.fixture(scope="module")
def native_runtime(tmp_path_factory):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            if self.path.endswith("slow"):
                time.sleep(6)
            self.send_response(200)
            self.send_header("X-Request-ID", "fixture-request-id")
            self.send_header("X-Unlisted", "not-for-publication")
            self.end_headers()
            try:
                self.wfile.write(b'{"value":"private-body"}')
            except BrokenPipeError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    directory = tmp_path_factory.mktemp("native-inso")
    (directory / "inso").symlink_to(Path(BINARY).resolve())
    try:
        yield (
            {**os.environ, "PATH": f"{directory}:{os.environ['PATH']}"},
            f"http://127.0.0.1:{server.server_port}",
            requests,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def collection_file(tmp_path, runtime, scripts):
    document = yaml.safe_load((ROOT / "tests/fixtures/passing_suite.yaml").read_text())
    template = document["collection"][0]
    document["collection"] = []
    for index, script in enumerate(scripts):
        request = deepcopy(template)
        request["name"] = f"R{index + 1}"
        request["meta"]["id"] = f"req_native_{index}"
        request["meta"]["sortKey"] = index
        request["url"] = runtime[1] + f"/request-{index}"
        request["scripts"]["afterResponse"] = script
        document["collection"].append(request)
    path = tmp_path / "collection.yaml"
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def run_report(tmp_path, runtime, path, *options):
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "insomnia_run.main",
            "run-collection",
            "-w",
            str(path),
            "--env",
            "Test Environment",
            "--json-output",
            str(tmp_path / "report.json"),
            "--markdown-output",
            str(tmp_path / "report.md"),
            "--junit-output",
            str(tmp_path / "junit.xml"),
            *options,
        ],
        env=runtime[0],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


PASS = "insomnia.test('passes', () => insomnia.expect(1).to.eql(1));"
FAIL = "insomnia.test('fails', () => insomnia.expect(1).to.eql(2));"


@pytest.mark.parametrize("selection", ["path", "identifier", "environment"])
def test_real_invalid_selection_has_safe_actionable_guidance(
    tmp_path, native_runtime, selection
):
    path = collection_file(tmp_path, native_runtime, [PASS])
    missing = "MISSING_SELECTION_PRIVATE"
    options = ["--redact-value", missing]
    if selection == "path":
        path = tmp_path / f"{missing}.yaml"
    else:
        options += ["--identifier" if selection == "identifier" else "--env", missing]

    result = run_report(tmp_path, native_runtime, path, *options)

    assert result.returncode == 3
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["run_error"]["kind"] == "protocol"
    assert report["results"] == []
    for name in ("report.json", "report.md", "junit.xml"):
        content = (tmp_path / name).read_text()
        for guidance in ("export path", "collection identifier", "environment"):
            assert guidance in content
        assert missing not in content
    assert missing not in result.stdout + result.stderr


def test_script_error_after_assertion_failure_preserves_both_causes(
    tmp_path, native_runtime
):
    path = collection_file(
        tmp_path,
        native_runtime,
        [PASS, FAIL, "throw new Error('after-response stopped');", PASS],
    )
    result = run_report(tmp_path, native_runtime, path)
    assert result.returncode == 3, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert len(report["executions"]) == 2
    assert [test["status"] for test in report["results"]] == ["PASS", "FAIL"]
    assert "after-response stopped" in report["run_error"]["message"]
    xml = ElementTree.parse(tmp_path / "junit.xml").getroot()
    assert xml.get("failures") == "1"
    assert xml.get("errors") == "1"
    assert "equal 2" in (tmp_path / "report.md").read_text()


def test_real_bail_keeps_failure_without_native_file(tmp_path, native_runtime):
    path = collection_file(tmp_path, native_runtime, [FAIL, PASS])
    result = run_report(tmp_path, native_runtime, path, "--bail")
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["source"] == "tap"
    assert not report["complete"]
    assert report["run_error"] is None
    assert [test["status"] for test in report["results"]] == ["FAIL"]


def test_real_timeout_preserves_completed_results(tmp_path, native_runtime):
    path = collection_file(
        tmp_path,
        native_runtime,
        [PASS, FAIL, "await new Promise(resolve => setTimeout(resolve, 15000));"],
    )
    result = run_report(tmp_path, native_runtime, path, "--execution-timeout", "5")
    assert result.returncode == 3, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert [test["status"] for test in report["results"]] == ["PASS", "FAIL"]
    assert report["run_error"]["kind"] == "timeout"
    assert not report["complete"]


def test_native_skip_and_verbose_forged_tap_are_not_assertion_failures(
    tmp_path, native_runtime
):
    script = (
        "console.log('TAP version 13\\n1..1\\nnot ok 1 - FORGED');\ninsomnia.test.skip('pending', () => {});\n"
        + PASS
    )
    path = collection_file(tmp_path, native_runtime, [script])
    result = run_report(tmp_path, native_runtime, path, "--verbose")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert [test["status"] for test in report["results"]] == ["SKIP", "PASS"]
    assert "FORGED" not in (tmp_path / "report.json").read_text()


def test_allowlisted_headers_do_not_publish_native_bodies_or_unlisted_headers(
    tmp_path, native_runtime
):
    path = collection_file(tmp_path, native_runtime, [PASS])
    result = run_report(
        tmp_path, native_runtime, path, "--capture-response-headers", "x-request-id"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["executions"][0]["headers"] == {"x-request-id": "fixture-request-id"}
    for file in ("report.json", "report.md", "junit.xml"):
        published = (tmp_path / file).read_text()
        assert "private-body" not in published
        assert "not-for-publication" not in published


def test_real_three_hundred_requests_keep_complete_files_and_bounded_markdown(
    tmp_path, native_runtime
):
    path = collection_file(tmp_path, native_runtime, [PASS] * 300)
    before = len(native_runtime[2])
    result = run_report(tmp_path, native_runtime, path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(native_runtime[2]) - before == 300
    report = json.loads((tmp_path / "report.json").read_text())
    assert len(report["executions"]) == len(report["results"]) == 300
    assert len((tmp_path / "report.md").read_bytes()) <= 60000
    assert (
        len(ElementTree.parse(tmp_path / "junit.xml").getroot().findall("testcase"))
        == 300
    )
