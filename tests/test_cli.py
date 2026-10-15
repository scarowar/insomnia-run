import json
import os
import subprocess
import sys
from unittest.mock import patch
from xml.etree import ElementTree

import pytest
from typer.testing import CliRunner

from insomnia_run.main import app
from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus


@pytest.mark.parametrize("command", ["run-collection", "run-test"])
@pytest.mark.parametrize("failure", ["missing", "permission", "format"])
@pytest.mark.parametrize("reporting", ["markdown", "json", "junit", "json-junit"])
def test_cli_startup_failure_is_fatal_without_publishing_reports(
    tmp_path, command, failure, reporting
):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    if failure != "missing":
        inso = fake_bin / "inso"
        inso.write_text("not an executable\n")
        inso.chmod(0o644 if failure == "permission" else 0o755)

    secret = "STARTUP_PRIVACY_SENTINEL_74193"
    junit = tmp_path / "report.xml"
    junit.write_text("previous report")
    args = [
        command,
        "-w",
        f"fixture-{secret}",
        "--identifier",
        secret,
        "--include-raw-output",
    ]
    if "json" in reporting:
        args.extend(["--output-format", "json"])
    if "junit" in reporting:
        args.extend(["--junit-output", str(junit)])

    result = subprocess.run(
        [sys.executable, "-m", "insomnia_run.main", *args],
        env={**os.environ, "PATH": str(fake_bin)},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Unable to execute Inso CLI" in result.stderr
    assert "Traceback" not in result.stderr
    assert secret not in result.stderr
    assert len(result.stderr) < 200
    assert junit.read_text() == "previous report"


@pytest.mark.parametrize("command", ["run-collection", "run-test"])
@pytest.mark.parametrize("error_type", [FileNotFoundError, PermissionError, OSError])
def test_cli_startup_diagnostic_does_not_echo_os_error_details(command, error_type):
    secret = "OS_ERROR_PRIVACY_SENTINEL_82194"
    with patch(
        "insomnia_run.runner.subprocess.Popen",
        side_effect=error_type(secret * 1000),
    ):
        result = CliRunner().invoke(app, [command, "-w", "fixture"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "Unable to execute Inso CLI" in result.stderr
    assert secret not in result.stderr
    assert len(result.stderr) < 200


@pytest.mark.parametrize(
    "command,method",
    [
        ("run-collection", "run_collection"),
        ("run-test", "run_test"),
    ],
)
@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("include_raw", [False, True])
def test_cli_reports_and_exit_codes(tmp_path, command, method, failed, include_raw):
    report = InsoRunReport(
        plan_end=1,
        raw_output="secret diagnostic",
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.FAIL if failed else InsoStatus.PASS,
                description="assertion",
            )
        ],
    )
    junit = tmp_path / "reports" / "junit.xml"
    args = [
        command,
        "-w",
        "fixture.yaml",
        "--output-format",
        "json",
        "--junit-output",
        str(junit),
    ]
    if include_raw:
        args.append("--include-raw-output")
    with patch(f"insomnia_run.main.InsoRunner.{method}", return_value=report):
        result = CliRunner().invoke(app, args)

    assert result.exit_code == int(failed), result.output
    payload = json.loads(result.stderr)
    assert payload["results"][0]["status"] == ("FAIL" if failed else "PASS")
    assert ("secret diagnostic" in result.stdout) is include_raw
    assert ("raw_output" in payload) is include_raw
    assert ElementTree.parse(junit).getroot().get("failures") == str(int(failed))


def test_invalid_env_var_does_not_execute_inso():
    with patch("insomnia_run.main.InsoRunner.run_collection") as run:
        result = CliRunner().invoke(
            app, ["run-collection", "-w", "fixture", "--env-var", "invalid"]
        )

    assert result.exit_code == 2
    run.assert_not_called()


def test_junit_write_failure_does_not_return_success(tmp_path):
    with patch(
        "insomnia_run.main.InsoRunner.run_collection",
        return_value=InsoRunReport(plan_end=0),
    ):
        result = CliRunner().invoke(
            app, ["run-collection", "-w", "fixture", "--junit-output", str(tmp_path)]
        )

    assert result.exit_code == 2
    assert "Unable to write JUnit report" in result.stderr


def test_cli_report_write_error_does_not_disclose_secret_arguments(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    inso = fake_bin / "inso"
    inso.write_text(
        "#!/usr/bin/env python3\nprint('TAP version 13\\n1..1\\nok 1 - passes')\n"
    )
    inso.chmod(0o755)
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("existing file")
    secret = "RUNTIME_PRIVACY_SENTINEL_39717"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "insomnia_run.main",
            "run-collection",
            "-w",
            "fixture",
            "--env-var",
            f"TOKEN={secret}",
            "--junit-output",
            str(blocked / "report.xml"),
        ],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert secret not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert "JUnit report" in result.stderr


def test_unexpected_cli_error_does_not_print_secret_locals():
    secret = "UNEXPECTED_ERROR_PRIVACY_SENTINEL_51409"
    script = """
from unittest.mock import patch
from insomnia_run.main import main

with patch('insomnia_run.main.InsoRunner.run_collection', side_effect=RuntimeError('Unexpected failure')):
    main()
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            "run-collection",
            "-w",
            "fixture",
            "--env-var",
            f"TOKEN={secret}",
        ],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode != 0
    assert "Unexpected failure" in result.stderr
    assert secret not in result.stdout + result.stderr


def test_environment_override_occurrences_reach_inso_unchanged(tmp_path, monkeypatch):
    captured = tmp_path / "arguments.json"
    inso = tmp_path / "inso"
    inso.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['CAPTURE_ARGUMENTS']).write_text(json.dumps(sys.argv[1:]))\n"
        "print('1..0')\n"
    )
    inso.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
    monkeypatch.setenv("CAPTURE_ARGUMENTS", str(captured))
    overrides = ["A=old&B=keep", "A=new", "ENCODED=one%2Btwo+words"]
    args = ["run-collection", "-w", "fixture"]
    for override in overrides:
        args.extend(["--env-var", override])

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 0, result.output
    arguments = json.loads(captured.read_text())
    assert [
        arguments[i + 1] for i, arg in enumerate(arguments) if arg == "--env-var"
    ] == overrides


@pytest.mark.parametrize("count", ["0", "-1"])
def test_invalid_iteration_count_is_rejected_before_execution(count):
    with patch(
        "insomnia_run.main.InsoRunner.run_collection",
        return_value=InsoRunReport(plan_end=0),
    ) as run:
        result = CliRunner().invoke(
            app, ["run-collection", "-w", "fixture", "--iteration-count", count]
        )

    assert result.exit_code == 2
    run.assert_not_called()


def test_invalid_env_var_error_does_not_echo_a_secret_value():
    secret = "PRIVACY_SENTINEL_WITHOUT_EQUALS"

    result = CliRunner().invoke(
        app, ["run-collection", "-w", "fixture", "--env-var", secret]
    )

    assert result.exit_code == 2
    assert secret not in result.output
    assert "KEY=VALUE" in result.output


@pytest.mark.parametrize(
    "command,method,option,value",
    [
        (command, method, option, value)
        for command, method in [
            ("run-collection", "run_collection"),
            ("run-test", "run_test"),
        ]
        for option, value in [
            ("--execution-timeout", "0"),
            ("--execution-timeout", "-1"),
            ("--request-timeout", "-1"),
        ]
    ]
    + [("run-collection", "run_collection", "--delay-request", "-1")],
)
def test_invalid_numeric_limits_are_rejected_before_execution(
    command, method, option, value
):
    with patch(
        f"insomnia_run.main.InsoRunner.{method}",
        return_value=InsoRunReport(plan_end=0),
    ) as run:
        result = CliRunner().invoke(app, [command, "-w", "fixture", option, value])

    assert result.exit_code == 2
    run.assert_not_called()
