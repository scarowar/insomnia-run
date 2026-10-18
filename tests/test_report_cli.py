import json
import os
import threading
from urllib.parse import quote
from xml.etree import ElementTree

import pytest
from typer.testing import CliRunner

from insomnia_run.main import app
from insomnia_run.models import (
    InsoResult,
    InsoRunReport,
    InsoStatus,
    RequestExecution,
    RunError,
)


@pytest.fixture
def report():
    return InsoRunReport(
        plan_end=1,
        target_name="Orders",
        source="native",
        executions=[RequestExecution(id=1, request_id="req_one", name="GET orders")],
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.PASS,
                description="returns orders",
                execution_id=1,
                duration_seconds=0.025,
            )
        ],
        raw_output="private diagnostics",
    )


def stub_runner(monkeypatch, report, *, command="run_collection", during_run=None):
    observed = []

    def run(self, options):
        observed.append(options)
        if during_run:
            during_run()
        return report

    monkeypatch.setattr(f"insomnia_run.main.InsoRunner.{command}", run)
    return observed


@pytest.mark.parametrize("command", ["run-collection", "run-test"])
def test_file_reports_are_independent_of_stderr(tmp_path, monkeypatch, report, command):
    stub_runner(monkeypatch, report, command=command.replace("-", "_"))
    destination = tmp_path / "reports"
    result = CliRunner().invoke(
        app,
        [
            command,
            "-w",
            "fixture",
            "--json-output",
            str(destination / "report.json"),
            "--markdown-output",
            str(destination / "report.md"),
            "--junit-output",
            str(destination / "report.xml"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    payload = json.loads((destination / "report.json").read_text())
    assert payload["schema_version"] == 1
    assert payload["results"][0]["duration_seconds"] == 0.025
    assert "raw_output" not in payload
    assert (destination / "report.md").read_text() == result.stdout
    assert ElementTree.parse(destination / "report.xml").getroot().get("tests") == "1"


@pytest.mark.parametrize(
    "status,run_error,expected",
    [
        (InsoStatus.PASS, None, 0),
        (InsoStatus.FAIL, None, 1),
        (InsoStatus.PASS, RunError(kind="timeout", message="Timed out"), 3),
        (InsoStatus.FAIL, RunError(kind="execution", message="Script error"), 3),
    ],
)
def test_cli_exit_policy_preserves_run_errors(
    monkeypatch, report, status, run_error, expected
):
    report.results[0].status = status
    report.run_error = run_error
    report.complete = run_error is None
    stub_runner(monkeypatch, report)

    result = CliRunner().invoke(
        app, ["run-collection", "-w", "fixture", "--output-format", "json"]
    )

    assert result.exit_code == expected, result.output
    assert json.loads(result.stderr)["run_error"] == (
        run_error.model_dump() if run_error else None
    )


def test_known_url_is_redacted_whole_across_publication_formats(
    tmp_path, monkeypatch, report
):
    value = "https://example.test/resource?token=token-value&customer=private-customer"
    report.target_name = report.raw_output = value
    report.results[0].status = InsoStatus.FAIL
    report.results[0].message = report.results[0].description = value
    report.executions[0].name = value
    report.executions[0].headers = {"x-request-id": value}
    stub_runner(monkeypatch, report)
    destinations = [
        tmp_path / name for name in ("report.json", "report.md", "junit.xml", "raw.txt")
    ]
    args = [
        "run-collection",
        "-w",
        "fixture",
        "--redact-value",
        value,
        "--include-raw-output",
        "--annotations",
        "--output-format",
        "json",
    ]
    for option, path in zip(
        ("--json-output", "--markdown-output", "--junit-output", "--raw-output-file"),
        destinations,
    ):
        args.extend([option, str(path)])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 1, result.output
    for published in [
        result.stdout,
        result.stderr,
        *(path.read_text() for path in destinations),
    ]:
        assert "private-customer" not in published
        assert "token-value" not in published


def test_legacy_verbose_is_rejected_before_execution(monkeypatch, report):
    observed = stub_runner(monkeypatch, report, command="run_test")

    result = CliRunner().invoke(app, ["run-test", "-w", "fixture", "--verbose"])

    assert result.exit_code == 2
    assert observed == []
    assert "verbose" in result.output.lower()


def test_colliding_output_files_are_rejected_before_execution(
    tmp_path, monkeypatch, report
):
    observed = stub_runner(monkeypatch, report)
    path = tmp_path / "same.json"

    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--json-output",
            str(path),
            "--markdown-output",
            str(path),
        ],
    )

    assert result.exit_code == 2
    assert observed == []
    assert not path.exists()


def test_file_write_failure_keeps_legacy_json_valid(tmp_path, monkeypatch, report):
    destination = tmp_path / "report.json"

    def obstruct_destination():
        destination.mkdir()

    stub_runner(monkeypatch, report, during_run=obstruct_destination)
    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--json-output",
            str(destination),
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stderr)["schema_version"] == 1
    assert "Unable to write" in result.stdout


def test_raw_file_is_explicit_and_does_not_enable_raw_json(
    tmp_path, monkeypatch, report
):
    stub_runner(monkeypatch, report)
    raw = tmp_path / "raw.log"

    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--raw-output-file",
            str(raw),
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert raw.read_text() == "private diagnostics"
    assert "raw_output" not in json.loads(result.stderr)
    assert "private diagnostics" not in result.stdout


def test_one_redacted_projection_is_used_for_every_sink(tmp_path, monkeypatch, report):
    secret = "sensitive" + " value/with+symbols"
    explicit = "manually" + " supplied"
    proxy_password = "proxy" + "pass999"
    encoded = quote(secret, safe="")
    leak = f"{secret} {encoded} {explicit} {proxy_password} https://user:{proxy_password}@proxy.invalid"
    report.target_name = leak
    report.executions[0].name = leak
    report.results[0].status = InsoStatus.FAIL
    report.results[0].description = leak
    report.results[0].message = leak
    report.raw_output = leak
    report.run_error = RunError(kind="execution", message=leak)
    original = report.model_dump_json()
    stub_runner(monkeypatch, report)
    outputs = [
        tmp_path / name
        for name in ("report.json", "report.md", "report.xml", "raw.log")
    ]

    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--env-var",
            f"TOKEN={encoded}",
            "--redact-value",
            explicit,
            "--http-proxy",
            f"https://user:{proxy_password}@proxy.invalid",
            "--json-output",
            str(outputs[0]),
            "--markdown-output",
            str(outputs[1]),
            "--junit-output",
            str(outputs[2]),
            "--raw-output-file",
            str(outputs[3]),
            "--include-raw-output",
            "--output-format",
            "json",
            "--annotations",
        ],
    )

    assert result.exit_code == 3, result.output
    published = (
        result.stdout + result.stderr + "".join(path.read_text() for path in outputs)
    )
    for value in (secret, encoded, explicit, proxy_password):
        assert value not in published
    assert report.model_dump_json() == original
    assert json.loads(result.stderr)["run_error"] is not None


def test_header_capture_is_collection_only_and_validated_before_execution(
    monkeypatch, report
):
    observed = stub_runner(monkeypatch, report)
    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--capture-response-headers",
            "Authorization",
        ],
    )
    assert result.exit_code == 2
    assert observed == []

    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--capture-response-headers",
            "X-Request-ID, Server",
        ],
    )
    assert result.exit_code == 0, result.output
    assert observed[-1].capture_response_headers == ["x-request-id", "server"]


def test_progress_never_enters_json_or_markdown_files(tmp_path, monkeypatch, report):
    stub_runner(monkeypatch, report)
    markdown = tmp_path / "report.md"
    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--progress",
            "--markdown-output",
            str(markdown),
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stderr)["schema_version"] == 1
    assert "Starting Inso" in result.stdout
    assert "Starting Inso" not in markdown.read_text()


def test_runner_validation_error_is_configuration_error_without_private_details(
    monkeypatch,
):
    def invalid(self, options):
        raise ValueError("private" + " sentinel")

    monkeypatch.setattr("insomnia_run.main.InsoRunner.run_collection", invalid)
    result = CliRunner().invoke(app, ["run-collection", "-w", "fixture"])

    assert result.exit_code == 2
    assert "private sentinel" not in result.output
    assert "Invalid Inso" in result.output


@pytest.mark.parametrize("command", ["run-collection", "run-test"])
def test_action_control_file_destination_is_rejected_before_execution(
    tmp_path, monkeypatch, report, command
):
    observed = stub_runner(monkeypatch, report, command=command.replace("-", "_"))
    control = tmp_path / "github-output"
    control.write_text("existing=untouched\n")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "temp"))
    monkeypatch.setenv("GITHUB_OUTPUT", str(control))

    result = CliRunner().invoke(
        app, [command, "-w", "fixture", "--json-output", str(control)]
    )

    assert result.exit_code == 2
    assert observed == []
    assert control.read_text() == "existing=untouched\n"


def test_destination_symlink_swap_is_rejected_after_execution(
    tmp_path, monkeypatch, report
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    directory = workspace / "reports"
    directory.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(workspace))
    monkeypatch.setenv("RUNNER_TEMP", str(workspace / "temp"))

    def swap_destination():
        directory.rmdir()
        directory.symlink_to(outside, target_is_directory=True)

    stub_runner(monkeypatch, report, during_run=swap_destination)
    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--json-output",
            str(directory / "report.json"),
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stderr)["schema_version"] == 1
    assert list(outside.iterdir()) == []


def test_progress_uses_stderr_for_the_action_file_protocol(
    tmp_path, monkeypatch, report
):
    stub_runner(monkeypatch, report)
    markdown = tmp_path / "report.md"

    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--markdown-output",
            str(markdown),
            "--progress",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Starting Inso execution." in result.stderr
    assert "Inso execution finished" in result.stderr
    assert "Starting Inso" not in result.stdout
    assert markdown.read_text() == result.stdout


def test_progress_heartbeat_uses_only_trusted_elapsed_time(monkeypatch, report):
    heartbeat_seen = threading.Event()
    from insomnia_run import main as cli

    echo = cli.typer.echo

    def capture_echo(message, **kwargs):
        echo(message, **kwargs)
        if str(message).startswith("Inso is running ("):
            heartbeat_seen.set()

    monkeypatch.setattr(cli.typer, "echo", capture_echo)
    monkeypatch.setattr(cli, "_PROGRESS_INTERVAL_SECONDS", 0.001)
    stub_runner(monkeypatch, report, during_run=lambda: heartbeat_seen.wait(2))

    result = CliRunner().invoke(app, ["run-collection", "-w", "fixture", "--progress"])

    assert result.exit_code == 0, result.output
    assert heartbeat_seen.is_set()
    assert "Inso is running (0s elapsed)." in result.stderr
    assert "request" not in result.stderr.lower()
    assert not any(
        thread.name == "insomnia-progress" for thread in threading.enumerate()
    )


@pytest.mark.parametrize("legacy_json", [False, True])
def test_annotations_are_bounded_escaped_and_separate_from_json(
    monkeypatch, report, legacy_json
):
    report.results = [
        InsoResult(
            id=index,
            status=InsoStatus.FAIL,
            description="bad%,:\r\n::warning::spoof",
            message="reason",
        )
        for index in range(1, 20)
    ]
    stub_runner(monkeypatch, report)
    args = ["run-collection", "-w", "fixture", "--annotations"]
    if legacy_json:
        args.extend(["--output-format", "json"])

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 1, result.output
    annotations = result.stdout if legacy_json else result.stderr
    commands = [
        line for line in annotations.splitlines() if line.startswith("::error ")
    ]
    assert len(commands) == 10
    assert "%25%2C%3A%0D%0A%3A%3Awarning%3A%3Aspoof" in commands[0]
    if legacy_json:
        assert json.loads(result.stderr)["schema_version"] == 1


def test_annotations_and_progress_are_disabled_by_default(monkeypatch, report):
    report.results[0].status = InsoStatus.FAIL
    stub_runner(monkeypatch, report)

    result = CliRunner().invoke(app, ["run-collection", "-w", "fixture"])

    assert result.exit_code == 1
    assert result.stderr == ""
    assert "::error" not in result.stdout
    assert "Starting Inso" not in result.stdout


def test_empty_header_capture_does_not_enable_full_data(monkeypatch, report):
    observed = stub_runner(monkeypatch, report)

    result = CliRunner().invoke(
        app, ["run-collection", "-w", "fixture", "--capture-response-headers", ""]
    )

    assert result.exit_code == 0, result.output
    assert observed[-1].capture_response_headers == []


def test_inherited_proxy_credentials_are_redacted(monkeypatch, report):
    password = "inherited" + "-proxy-credential"
    monkeypatch.setenv("https_proxy", f"http://user:{password}@proxy.invalid")
    report.results[0].description = password
    stub_runner(monkeypatch, report)

    result = CliRunner().invoke(
        app, ["run-collection", "-w", "fixture", "--output-format", "json"]
    )

    assert result.exit_code == 0, result.output
    assert password not in result.stdout + result.stderr


def test_junit_write_error_does_not_block_other_reports(tmp_path, monkeypatch, report):
    from insomnia_run import main as cli

    write = cli.write_report_file

    def block_junit(path, text, **kwargs):
        if str(path).endswith(".xml"):
            raise PermissionError("private" + " diagnostic")
        return write(path, text, **kwargs)

    monkeypatch.setattr(cli, "write_report_file", block_junit)
    stub_runner(monkeypatch, report)
    destination = tmp_path / "report.json"
    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--junit-output",
            str(tmp_path / "report.xml"),
            "--json-output",
            str(destination),
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stderr) == json.loads(destination.read_text())
    assert "private diagnostic" not in result.output


@pytest.mark.parametrize("command", ["run-collection", "run-test"])
def test_file_reports_are_private(tmp_path, monkeypatch, report, command):
    stub_runner(monkeypatch, report, command=command.replace("-", "_"))
    destination = tmp_path / "report.json"
    result = CliRunner().invoke(
        app, [command, "-w", "fixture", "--json-output", str(destination)]
    )

    assert result.exit_code == 0, result.output
    assert os.stat(destination).st_mode & 0o777 == 0o600


@pytest.mark.parametrize("renderer", ["generate_markdown", "generate_junit"])
def test_rendering_failure_preserves_normalized_json(
    tmp_path, monkeypatch, report, renderer
):
    def fail_render(*args, **kwargs):
        raise ValueError("private" + " rendering diagnostic")

    monkeypatch.setattr(f"insomnia_run.main.Reporter.{renderer}", fail_render)
    stub_runner(monkeypatch, report)
    destination = tmp_path / "report.json"

    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--json-output",
            str(destination),
            "--junit-output",
            str(tmp_path / "report.xml"),
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stderr) == json.loads(destination.read_text())
    assert "private rendering diagnostic" not in result.output


def test_url_form_environment_override_values_are_redacted(monkeypatch, report):
    first = "first" + " component value"
    second = "second" + " component/value"
    report.results[0].description = f"{first} {second}"
    stub_runner(monkeypatch, report)

    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--env-var",
            f"A={quote(first)}&B={quote(second)}",
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert first not in result.stdout + result.stderr
    assert second not in result.stdout + result.stderr


def test_missing_distribution_metadata_has_a_stable_version_fallback(monkeypatch):
    from importlib.metadata import PackageNotFoundError

    def unavailable(name):
        raise PackageNotFoundError(name)

    monkeypatch.setattr("insomnia_run.main.importlib.metadata.version", unavailable)
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == "insomnia-run unknown\n"


def test_malformed_proxy_does_not_disclose_parser_details(monkeypatch, report):
    stub_runner(monkeypatch, report)
    result = CliRunner().invoke(
        app,
        [
            "run-collection",
            "-w",
            "fixture",
            "--http-proxy",
            "http://[invalid",
            "--output-format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stderr)["schema_version"] == 1
    assert "invalid" not in result.output.lower()
