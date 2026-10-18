"""Exercise action publication through its Python adapter and composite shell."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from xml.etree import ElementTree

import pytest
import yaml

from insomnia_run import action_runtime


ROOT = Path(__file__).resolve().parents[1]


def load_action():
    return yaml.safe_load((ROOT / "action.yml").read_text())


def read_outputs(path):
    outputs = {}
    lines = iter(path.read_text().splitlines())
    for line in lines:
        if "<<" in line:
            key, delimiter = line.split("<<", 1)
            value = []
            for item in lines:
                if item == delimiter:
                    break
                value.append(item)
            else:
                raise AssertionError("Unterminated action output")
            outputs[key] = "\n".join(value)
        else:
            key, value = line.split("=", 1)
            outputs[key] = value
    return outputs


def action_environment(tmp_path):
    action = load_action()
    step = next(s for s in action["runs"]["steps"] if s.get("id") == "run-cli")
    env = os.environ.copy()
    for key, value in step["env"].items():
        match = re.fullmatch(r"\$\{\{ inputs\.([\w-]+) \}\}", value)
        env[key] = str(action["inputs"][match[1]].get("default", "")) if match else ""
    env.update(
        RUNNER_TEMP=str(tmp_path),
        COMMAND="collection",
        WORKING_DIR="fixture.yaml",
        INSOMNIA_RUN_VENV=str(Path(sys.executable).parent.parent),
        GITHUB_ACTIONS="true",
        GITHUB_WORKSPACE=str(tmp_path),
        GITHUB_SERVER_URL="https://github.com",
        GITHUB_OUTPUT=str(tmp_path / "outputs"),
        GITHUB_STEP_SUMMARY=str(tmp_path / "summary"),
        PYTHONPATH=str(ROOT / "src"),
    )
    return env


FAKE_INSO = r"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
if args == ['--version']:
    print('13.3.1')
    sys.exit(0)
if '--help' in args:
    print('  --output <path>  Write native JSON report')
    sys.exit(0)
if os.environ.get('TEST_ENV_FILE'):
    Path(os.environ['TEST_ENV_FILE']).write_text(json.dumps({
        'args': args, 'proxy': os.environ.get('HTTPS_PROXY'),
        'selected_binary': str(Path(sys.argv[0]).resolve()),
        'telemetry': os.environ.get('INSO_TELEMETRY_DISABLED'),
    }))
mode = os.environ.get('TEST_OUTCOME', 'pass')
statuses = ['passed', 'failed' if mode == 'fail' else 'passed', 'skipped']
names = ['returns orders', 'validates status', 'optional field']
tests = [dict(testCase=name, status=status, executionTime=2.5)
         for name, status in zip(names, statuses)]
if mode == 'fail':
    tests[1]['errorMessage'] = 'Expected status 200; received 500'
native = {
    'executions': [
        {'request': {'_id': 'req_one', 'name': 'GET orders'},
         'response': {'code': 200, 'status': 'OK', 'responseTime': 25,
                      'headers': {'X-Request-ID': 'trace-one',
                                  'Server': 'test-server',
                                  'X-Unselected': 'not-published'}},
         'tests': tests[:2], 'iteration': 0},
        {'request': {'_id': 'req_two', 'name': 'GET optional'},
         'response': {'code': 204, 'responseTime': 10},
         'tests': tests[2:], 'iteration': 0},
    ],
    'error': 'Request script failed' if mode == 'execution' else None,
}
print('TAP version 13')
print('1..3')
for index, (name, status) in enumerate(zip(names, statuses), 1):
    prefix = 'not ok' if status == 'failed' else 'ok'
    print(f'{prefix} {index} - {name}' + (' # SKIP optional' if status == 'skipped' else ''))
print('# private raw diagnostic')
if '--output' in args:
    Path(args[args.index('--output') + 1]).write_text(json.dumps(native))
sys.exit(1 if mode in ('fail', 'execution') else 0)
"""


@pytest.fixture
def run_action(tmp_path):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    inso = fake_bin / "inso"
    inso.write_text(FAKE_INSO)
    inso.chmod(0o755)

    def run(**overrides):
        env = action_environment(tmp_path)
        env["PATH"] = f"{fake_bin}:{os.environ['PATH']}"
        env.update(overrides)
        step = next(
            s for s in load_action()["runs"]["steps"] if s.get("id") == "run-cli"
        )
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    return run


@pytest.fixture
def adapter_process(tmp_path, monkeypatch):
    """Replace only the child CLI, leaving file validation/publication real."""
    calls = []

    def run(
        *,
        payload=None,
        child_exit=0,
        write_json=True,
        write_junit=True,
        write_markdown=True,
        write_raw=True,
        child_stdout="",
        child_stderr="",
        during_run=None,
        entrypoint=False,
        **overrides,
    ):
        env = action_environment(tmp_path)
        env.update(overrides)
        if payload is None:
            payload = json.dumps(
                {
                    "plan_end": 1,
                    "results": [
                        {
                            "id": 1,
                            "status": "FAIL" if child_exit == 1 else "PASS",
                            "description": "works",
                        }
                    ],
                }
            )

        def child(args, *, stdout, check, env):
            calls.append((args, env))
            assert args[:4] == [
                sys.executable,
                "-m",
                "insomnia_run.main",
                f"run-{env['COMMAND']}",
            ]
            if write_json:
                Path(args[args.index("--json-output") + 1]).write_text(payload)
            if write_markdown:
                Path(args[args.index("--markdown-output") + 1]).write_text(
                    "## File report\n"
                )
            if write_junit and "--junit-output" in args:
                Path(args[args.index("--junit-output") + 1]).write_text(
                    '<testsuite tests="1" />'
                )
            if write_raw and "--raw-output-file" in args:
                Path(args[args.index("--raw-output-file") + 1]).write_text(
                    "raw diagnostic"
                )
            if during_run:
                during_run()
            stdout.write(child_stdout)
            if child_stderr:
                print(child_stderr, file=sys.stderr)
            return subprocess.CompletedProcess(args, child_exit)

        monkeypatch.setattr(action_runtime.subprocess, "run", child)
        if entrypoint:
            monkeypatch.setattr(action_runtime.os, "environ", env)
            action_runtime.main()
        return action_runtime.run_action(env)

    return run, calls


@pytest.mark.parametrize(
    "payload",
    [
        "invalid\n::warning::INJECTED",
        "invalid\r::error::INJECTED",
        "%0A::notice::INJECTED",
    ],
)
def test_invalid_command_is_not_echoed_as_a_workflow_command(run_action, payload):
    result = run_action(COMMAND=payload)

    assert result.returncode == 2
    assert "Invalid command" in result.stdout
    assert "INJECTED" not in result.stdout + result.stderr


@pytest.mark.parametrize("command", ["collection", "test"])
@pytest.mark.parametrize("outcome,expected_exit", [("pass", "0"), ("fail", "1")])
def test_composite_runs_real_cli_and_publishes_matching_files(
    run_action, tmp_path, command, outcome, expected_exit
):
    result = run_action(COMMAND=command, OUTPUT_FORMAT="json", TEST_OUTCOME=outcome)

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["exit-code"] == expected_exit
    reports = Path(outputs["report-directory"])
    payload = json.loads(outputs["json-output"])
    assert payload == json.loads(Path(outputs["json-file"]).read_text())
    assert payload["schema_version"] == 1
    assert payload["run_type"] == command
    assert outputs["markdown"] == (reports / "report.md").read_text()
    assert (reports / "report.md").read_text() == (tmp_path / "summary").read_text()
    assert ElementTree.parse(reports / "junit.xml").getroot().get("tests") == "3"
    assert (
        Path(outputs["junit-file"]).read_bytes() == (reports / "junit.xml").read_bytes()
    )
    assert outputs["total"] == "3"
    assert outputs["passed"] == ("2" if outcome == "pass" else "1")
    assert outputs["failed"] == expected_exit
    assert outputs["skipped"] == "1"
    assert outputs["requests"] == ("2" if command == "collection" else "")
    assert outputs["run-error"] == "false"
    assert outputs["json-output-omitted"] == "false"
    assert "Starting Inso execution." in result.stderr
    assert "Inso execution finished" in result.stderr
    assert "Starting Inso" not in outputs["markdown"]
    if outcome == "fail":
        assert any(line.startswith("::error ") for line in result.stderr.splitlines())
    else:
        assert not any(
            line.startswith("::error ") for line in result.stderr.splitlines()
        )


@pytest.mark.parametrize("cli_exit", [0, 1, 2, 3, 127])
def test_adapter_preserves_child_exit_codes(adapter_process, tmp_path, cli_exit):
    run, _ = adapter_process
    assert run(child_exit=cli_exit) == 0
    assert read_outputs(tmp_path / "outputs")["exit-code"] == str(cli_exit)


@pytest.mark.parametrize(
    "fail_on_error", ["true", "false", "TRUE", "True", "FALSE", "False", "", "typo"]
)
@pytest.mark.parametrize("cli_exit", ["0", "1", "2", "3", "127", ""])
def test_final_failure_policy_only_allows_assertion_failures_to_be_ignored(
    fail_on_error, cli_exit
):
    final_step = next(
        s
        for s in load_action()["runs"]["steps"]
        if s.get("name") == "Check for Failures"
    )
    decision = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", final_step["run"]],
        env={**os.environ, "EXIT_CODE": cli_exit, "FAIL_ON_ERROR": fail_on_error},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    allowed = cli_exit == "0" or (cli_exit == "1" and fail_on_error.lower() == "false")
    assert (decision.returncode == 0) is allowed


def test_real_execution_error_cannot_be_ignored_as_an_assertion_failure(
    run_action, tmp_path
):
    result = run_action(TEST_OUTCOME="execution")

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["exit-code"] == "3"
    assert outputs["run-error"] == "true"
    assert (
        json.loads(Path(outputs["json-file"]).read_text())["run_error"]["kind"]
        == "execution"
    )


@pytest.mark.parametrize("failed_file", ["GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"])
def test_action_fails_when_publishing_reports_fails(run_action, tmp_path, failed_file):
    result = run_action(**{failed_file: str(tmp_path)})
    assert result.returncode == 2


@pytest.mark.parametrize(
    "payload", ["", "not JSON", "{}", "[]", '{"plan_end": "invalid"}']
)
@pytest.mark.parametrize("cli_exit", [0, 1])
def test_malformed_file_json_is_not_published_or_replaced_with_stderr(
    adapter_process, tmp_path, capfd, payload, cli_exit
):
    run, _ = adapter_process
    diagnostic = "private child diagnostic"
    assert (
        run(
            payload=payload,
            child_exit=cli_exit,
            child_stderr=diagnostic,
            OUTPUT_FORMAT="json",
        )
        == 0
    )

    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["exit-code"] == "2"
    assert outputs["json-output"] == ""
    assert outputs["json-file"] == ""
    assert outputs["report-directory"] == ""
    assert outputs["markdown"] == ""
    assert outputs["total"] == ""
    assert diagnostic not in outputs["markdown"]
    assert diagnostic not in (tmp_path / "summary").read_text()
    assert diagnostic in capfd.readouterr().err


@pytest.mark.parametrize("cli_exit", [0, 1, 2, 3, 127])
def test_missing_json_is_a_report_error_without_masking_execution_errors(
    adapter_process, tmp_path, cli_exit
):
    run, _ = adapter_process
    assert run(write_json=False, child_exit=cli_exit, OUTPUT_FORMAT="json") == 0
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["exit-code"] == str(max(2, cli_exit))
    assert outputs["json-output"] == outputs["json-file"] == ""


@pytest.mark.parametrize("missing", ["write_junit", "write_markdown"])
@pytest.mark.parametrize("child_exit", [0, 1])
def test_missing_requested_report_file_is_a_publication_error(
    adapter_process, tmp_path, missing, child_exit
):
    run, _ = adapter_process
    assert run(**{missing: False}, child_exit=child_exit) == 0

    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["exit-code"] == "2"
    assert Path(outputs["json-file"]).is_file()


def test_child_stdout_is_not_replayed_as_workflow_commands(
    adapter_process, tmp_path, capfd
):
    run, _ = adapter_process
    assert run(child_stdout="::error::FORGED\nexit-code=0") == 0
    captured = capfd.readouterr()
    assert "FORGED" not in captured.out + captured.err
    assert "FORGED" not in read_outputs(tmp_path / "outputs")["markdown"]


@pytest.mark.parametrize("child_exit,status", [(0, "FAIL"), (1, "PASS")])
def test_exit_and_report_disagreement_is_a_wrapper_error(
    adapter_process, tmp_path, child_exit, status
):
    run, _ = adapter_process
    payload = json.dumps(
        {"plan_end": 1, "results": [{"id": 1, "status": status, "description": "test"}]}
    )
    assert run(payload=payload, child_exit=child_exit) == 0
    assert read_outputs(tmp_path / "outputs")["exit-code"] == "2"


def test_trusted_stderr_progress_and_annotations_are_preserved(
    adapter_process, tmp_path, capfd
):
    run, _ = adapter_process
    trusted = (
        "Starting Inso execution.\n"
        "Inso is running (10s elapsed).\n"
        "::error title=Insomnia assertion::Expected status 200.\n"
    )
    assert run(child_stderr=trusted, child_stdout="::error::FORGED", child_exit=1) == 0
    captured = capfd.readouterr()
    assert trusted in captured.err
    assert "FORGED" not in captured.out + captured.err
    assert "Starting Inso" not in read_outputs(tmp_path / "outputs")["markdown"]


@pytest.mark.parametrize("variable", ["COMMAND", "OUTPUT_FORMAT"])
def test_adapter_rejects_invalid_config_before_launch(adapter_process, capfd, variable):
    run, calls = adapter_process
    assert run(**{variable: "invalid\n::error::FORGED"}) == 2
    assert calls == []
    captured = capfd.readouterr()
    assert "FORGED" not in captured.out + captured.err


@pytest.mark.parametrize("days", ["0", "401", "bad", "\u0661\u0664"])
def test_adapter_rejects_retention_before_creating_reports(
    adapter_process, tmp_path, capfd, days
):
    run, calls = adapter_process
    assert run(UPLOAD_ARTIFACT="true", ARTIFACT_RETENTION_DAYS=days) == 2
    assert calls == []
    assert not list(tmp_path.glob("insomnia-run-reports.*"))
    assert "artifact-retention-days" in capfd.readouterr().out


@pytest.mark.parametrize("server", ["https://github.com", "https://octocorp.ghe.com"])
def test_adapter_accepts_supported_artifact_servers(adapter_process, server):
    run, calls = adapter_process
    assert run(UPLOAD_ARTIFACT="true", GITHUB_SERVER_URL=server) == 0
    assert len(calls) == 1


def test_adapter_rejects_unsupported_artifact_server_without_creating_reports(
    adapter_process, tmp_path, capfd
):
    run, calls = adapter_process
    assert (
        run(UPLOAD_ARTIFACT="true", GITHUB_SERVER_URL="https://github.example.test")
        == 2
    )
    assert calls == []
    assert not list(tmp_path.glob("insomnia-run-reports.*"))
    assert "artifact" in capfd.readouterr().out.lower()


def test_adapter_maps_raw_capture_to_an_explicit_file(adapter_process, tmp_path):
    run, calls = adapter_process
    assert run(INCLUDE_RAW_OUTPUT="true") == 0
    args = calls[0][0]
    directory = Path(read_outputs(tmp_path / "outputs")["report-directory"])
    assert "--include-raw-output" in args
    assert args[args.index("--raw-output-file") + 1] == str(directory / "raw.txt")
    assert read_outputs(tmp_path / "outputs")["raw-file"] == str(directory / "raw.txt")
    assert (directory / "raw.txt").read_text() == "raw diagnostic"


def test_adapter_outputs_native_request_count_and_run_error(adapter_process, tmp_path):
    run, _ = adapter_process
    payload = json.dumps(
        {
            "plan_end": 0,
            "source": "native",
            "executions": [{"id": 1, "name": "GET orders"}],
            "complete": False,
            "run_error": {"kind": "execution", "message": "Script failed"},
        }
    )
    assert run(payload=payload, child_exit=3) == 0
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["requests"] == "1"
    assert outputs["run-error"] == "true"
    assert outputs["total"] == outputs["passed"] == outputs["failed"] == "0"


@pytest.mark.parametrize("child_exit", [0, 1, 2, 3])
def test_adapter_entrypoint_completes_publication_before_final_policy(
    adapter_process, tmp_path, child_exit
):
    run, _ = adapter_process
    with pytest.raises(SystemExit) as error:
        run(entrypoint=True, child_exit=child_exit)
    assert error.value.code == 0
    assert read_outputs(tmp_path / "outputs")["exit-code"] == str(child_exit)


@pytest.mark.parametrize("control", ["GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"])
def test_adapter_entrypoint_reports_publication_io_failure(
    adapter_process, tmp_path, capfd, control
):
    run, _ = adapter_process
    with pytest.raises(SystemExit) as error:
        run(entrypoint=True, **{control: str(tmp_path)})
    assert error.value.code == 2
    assert "Unable to execute or publish" in capfd.readouterr().out


def test_output_delimiter_collision_cannot_inject_values(tmp_path, monkeypatch):
    delimiters = iter(["collision", "safe", "final"])
    monkeypatch.setattr(
        action_runtime.secrets, "token_hex", lambda size: next(delimiters)
    )
    values = {"markdown": "collision\nexit-code=0\n", "exit-code": "3"}
    action_runtime.write_outputs(tmp_path / "outputs", values)
    assert read_outputs(tmp_path / "outputs") == values


def test_reports_are_fresh_for_each_invocation(adapter_process, tmp_path):
    run, _ = adapter_process
    assert run() == 0
    first = read_outputs(tmp_path / "outputs")
    assert (
        run(child_exit=2, write_json=False, write_junit=False, write_markdown=False)
        == 0
    )
    second = read_outputs(tmp_path / "outputs")

    assert first["report-directory"] != second["report-directory"]
    assert second["junit-file"] == second["json-file"] == second["markdown"] == ""
    assert not (Path(second["report-directory"]) / "junit.xml").exists()
    assert Path(first["junit-file"]).is_file()


@pytest.mark.parametrize("enabled", ["false", "true", "TRUE"])
def test_raw_output_requires_explicit_opt_in(run_action, tmp_path, enabled):
    result = run_action(INCLUDE_RAW_OUTPUT=enabled, OUTPUT_FORMAT="json")

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(tmp_path / "outputs")
    report_dir = Path(outputs["report-directory"])
    payload = json.loads(outputs["json-output"])
    if enabled.lower() == "true":
        assert (
            Path(outputs["raw-file"]).read_text().endswith("# private raw diagnostic\n")
        )
        assert "private raw diagnostic" in payload["raw_output"]
        assert Path(outputs["raw-file"]).stat().st_mode & 0o777 == 0o600
    else:
        assert outputs["raw-file"] == ""
        assert not (report_dir / "raw.txt").exists()
        assert "raw_output" not in payload
        assert "private raw diagnostic" not in outputs["markdown"]


def test_custom_junit_is_a_copy_of_the_fresh_canonical_report(run_action, tmp_path):
    destination = tmp_path / "custom" / "junit.xml"
    result = run_action(JUNIT_OUTPUT_FILE=str(destination))

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["junit-file"] == str(destination)
    assert (
        destination.read_bytes()
        == (Path(outputs["report-directory"]) / "junit.xml").read_bytes()
    )
    assert destination.stat().st_mode & 0o777 == 0o600


def test_custom_junit_relative_path_is_resolved_within_workspace(run_action, tmp_path):
    result = run_action(JUNIT_OUTPUT_FILE="reports/junit.xml")

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(tmp_path / "outputs")
    destination = tmp_path / "reports" / "junit.xml"
    assert outputs["junit-file"] == str(destination)
    assert (
        destination.read_bytes()
        == (Path(outputs["report-directory"]) / "junit.xml").read_bytes()
    )


def test_custom_junit_path_does_not_publish_a_previous_report(
    adapter_process, tmp_path
):
    run, _ = adapter_process
    destination = tmp_path / "custom.xml"
    destination.write_text("previous report must not be uploaded")

    assert run(JUNIT_OUTPUT_FILE=str(destination), write_junit=False, child_exit=2) == 0

    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["junit-file"] == ""
    assert not (Path(outputs["report-directory"]) / "junit.xml").exists()
    assert destination.read_text() == "previous report must not be uploaded"


def test_failed_custom_junit_copy_keeps_canonical_upload(adapter_process, tmp_path):
    run, _ = adapter_process
    destination = tmp_path / "custom.xml"

    assert run(JUNIT_OUTPUT_FILE=str(destination), during_run=destination.mkdir) == 0

    outputs = read_outputs(tmp_path / "outputs")
    canonical = Path(outputs["report-directory"]) / "junit.xml"
    assert outputs["exit-code"] == "2"
    assert canonical.read_text() == '<testsuite tests="1" />'
    assert outputs["junit-file"] == str(canonical)


@pytest.mark.parametrize(
    "control",
    [
        "GITHUB_OUTPUT",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_ENV",
        "GITHUB_PATH",
        "GITHUB_STATE",
        "GITHUB_EVENT_PATH",
    ],
)
def test_custom_junit_cannot_overwrite_action_control_files_before_launch(
    run_action, tmp_path, control
):
    control_path = tmp_path / control
    control_path.write_text("untouched\n")
    captured = tmp_path / "executed.json"
    result = run_action(
        **{
            control: str(control_path),
            "JUNIT_OUTPUT_FILE": str(control_path),
            "TEST_ENV_FILE": str(captured),
        }
    )

    assert result.returncode == 2
    assert control_path.read_text() == "untouched\n"
    assert not captured.exists()


@pytest.mark.parametrize(
    "report_name", ["report.json", "report.md", "junit.xml", "raw.txt"]
)
def test_custom_junit_cannot_collide_with_any_canonical_report(
    adapter_process, tmp_path, monkeypatch, report_name
):
    run, calls = adapter_process
    reports = tmp_path / "fixed-reports"
    reports.mkdir()
    monkeypatch.setattr(
        action_runtime.tempfile, "mkdtemp", lambda **kwargs: str(reports)
    )

    assert run(JUNIT_OUTPUT_FILE=str(reports / report_name)) == 2
    assert calls == []
    assert list(reports.iterdir()) == []


def test_custom_junit_rejects_symlink_escape_before_launch(run_action, tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "escape"
    link.symlink_to(outside, target_is_directory=True)
    captured = tmp_path / "executed.json"
    result = run_action(
        JUNIT_OUTPUT_FILE=str(link / "junit.xml"), TEST_ENV_FILE=str(captured)
    )

    assert result.returncode == 2
    assert not captured.exists()
    assert list(outside.iterdir()) == []


def test_custom_junit_path_cannot_inject_an_action_output(run_action, tmp_path):
    captured = tmp_path / "executed.json"
    destination = tmp_path / "junit.xml\nexit-code=0"
    result = run_action(JUNIT_OUTPUT_FILE=str(destination), TEST_ENV_FILE=str(captured))

    assert result.returncode == 2
    assert not captured.exists()
    assert not destination.exists()
    assert "exit-code=0" not in result.stdout + result.stderr


def test_junit_can_be_disabled_without_disabling_other_reports(run_action, tmp_path):
    result = run_action(
        JUNIT_REPORT="false", JUNIT_OUTPUT_FILE=str(tmp_path / "outputs")
    )

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["junit-file"] == ""
    assert not (Path(outputs["report-directory"]) / "junit.xml").exists()
    assert Path(outputs["json-file"]).is_file()


@pytest.mark.parametrize("days", ["0", "401", "invalid", "-1", "1.0", "\u0661\u0664"])
def test_artifact_retention_is_validated_before_launch(run_action, tmp_path, days):
    captured = tmp_path / "executed.json"
    result = run_action(
        UPLOAD_ARTIFACT="true",
        ARTIFACT_RETENTION_DAYS=days,
        TEST_ENV_FILE=str(captured),
    )

    assert result.returncode == 2
    assert "artifact-retention-days" in result.stdout
    assert not captured.exists()
    assert not list(tmp_path.glob("insomnia-run-reports.*"))


@pytest.mark.parametrize("days", ["1", "400"])
@pytest.mark.parametrize("server", ["https://github.com", "https://octocorp.ghe.com"])
def test_artifact_upload_supports_public_and_enterprise_cloud(run_action, server, days):
    result = run_action(
        UPLOAD_ARTIFACT="true", GITHUB_SERVER_URL=server, ARTIFACT_RETENTION_DAYS=days
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "server",
    [
        "https://github.example.test",
        "http://github.com",
        "https://github.com.evil.test",
        "https://ghe.com",
        "https://evilghe.com",
        "https://org.ghe.com.evil.test",
        "https://user@org.ghe.com",
        "https://org.ghe.com:8443",
        "https://org.ghe.com/path",
        "https://org.ghe.com?query=1",
        "https://org.ghe.com#fragment",
        "https://org.ghe.com\\evil",
    ],
)
def test_builtin_artifacts_reject_ghes_and_ambiguous_cloud_urls(
    run_action, tmp_path, server
):
    captured = tmp_path / "executed.json"
    result = run_action(
        UPLOAD_ARTIFACT="true", GITHUB_SERVER_URL=server, TEST_ENV_FILE=str(captured)
    )

    assert result.returncode == 2
    assert not captured.exists()
    assert "artifact" in result.stdout.lower()


def test_ghes_can_use_reports_without_builtin_artifacts(run_action):
    result = run_action(
        UPLOAD_ARTIFACT="false", GITHUB_SERVER_URL="https://github.example.test"
    )
    assert result.returncode == 0, result.stderr


def test_inherited_proxy_and_explicit_proxy_have_separate_channels(
    run_action, tmp_path
):
    captured = tmp_path / "env.json"
    result = run_action(
        HTTPS_PROXY="http://enterprise.proxy:8080",
        INPUT_HTTPS_PROXY="http://override.proxy:8080",
        TEST_ENV_FILE=str(captured),
    )

    assert result.returncode == 0, result.stderr
    observed = json.loads(captured.read_text())
    assert observed["proxy"] == "http://enterprise.proxy:8080"
    assert (
        observed["args"][observed["args"].index("--httpsProxy") + 1]
        == "http://override.proxy:8080"
    )
    assert observed["telemetry"] == "1"


@pytest.mark.parametrize("use_installed", ["true", "false"])
def test_composite_uses_selected_inso_without_stale_path_shadowing(
    run_action, tmp_path, use_installed
):
    installed_bin = tmp_path / "insomnia-run-inso" / "bin"
    installed_bin.mkdir(parents=True)
    installed = installed_bin / "inso"
    installed.write_text(FAKE_INSO)
    installed.chmod(0o755)
    captured = tmp_path / "selected.json"

    result = run_action(USE_INSTALLED_INSO=use_installed, TEST_ENV_FILE=str(captured))

    assert result.returncode == 0, result.stderr
    expected = installed if use_installed == "true" else tmp_path / "fake-bin" / "inso"
    assert json.loads(captured.read_text())["selected_binary"] == str(expected)


def test_header_allowlist_reaches_real_cli_projection(run_action, tmp_path):
    captured = tmp_path / "args.json"
    result = run_action(
        CAPTURE_RESPONSE_HEADERS="X-Request-ID, Server", TEST_ENV_FILE=str(captured)
    )

    assert result.returncode == 0, result.stderr
    observed = json.loads(captured.read_text())["args"]
    assert observed[observed.index("--includeFullData") + 1] == "redact"
    assert "--acceptRisk" in observed
    outputs = read_outputs(tmp_path / "outputs")
    report = json.loads(Path(outputs["json-file"]).read_text())
    assert report["executions"][0]["headers"] == {
        "x-request-id": "trace-one",
        "server": "test-server",
    }
    assert "not-published" not in Path(outputs["json-file"]).read_text()


@pytest.mark.parametrize("header", ["Authorization", "Set-Cookie", "*", "X-API-Key"])
def test_credential_headers_are_rejected_before_inso_launch(
    run_action, tmp_path, header
):
    captured = tmp_path / "executed.json"
    result = run_action(CAPTURE_RESPONSE_HEADERS=header, TEST_ENV_FILE=str(captured))

    assert result.returncode == 0, result.stderr
    assert read_outputs(tmp_path / "outputs")["exit-code"] == "2"
    assert not captured.exists()


@pytest.mark.parametrize("command", ["collection", "test"])
def test_adapter_maps_every_common_input_without_shell_interpretation(
    adapter_process, tmp_path, command
):
    run, calls = adapter_process
    valued = {
        "WORKING_DIR": ("--working-dir", "folder with spaces/export.yaml"),
        "IDENTIFIER": ("--identifier", "--literal $(touch SHOULD_NOT_EXIST)"),
        "ENVIRONMENT": ("--env", "staging's environment"),
        "REQUEST_TIMEOUT": ("--request-timeout", "0"),
        "EXECUTION_TIMEOUT": ("--execution-timeout", "42"),
        "INPUT_HTTPS_PROXY": ("--https-proxy", "http://https.proxy:3128"),
        "INPUT_HTTP_PROXY": ("--http-proxy", "http://http.proxy:3128"),
        "INPUT_NO_PROXY": ("--no-proxy", "localhost,127.0.0.1"),
        "WORKFLOW_URL": ("--workflow-url", "https://github.com/o/r/actions/runs/1"),
    }
    overrides = {key: value for key, (_, value) in valued.items()}
    overrides.update(
        COMMAND=command,
        BAIL="true",
        DISABLE_CERT_VALIDATION="TRUE",
        VERBOSE="true",
        PROGRESS="true",
        ANNOTATIONS="true",
        DATA_FOLDERS="  a' b  , \\path\\  ",
        REDACT_VALUES="first value\nsecond value",
    )

    assert run(**overrides) == 0

    args = calls[0][0]
    for option, value in valued.values():
        assert args[args.index(option) + 1] == value
    for flag in (
        "--bail",
        "--disable-cert-validation",
        "--verbose",
        "--progress",
        "--annotations",
    ):
        assert flag in args
    assert [
        args[index + 1] for index, item in enumerate(args) if item == "--data-folders"
    ] == ["a' b", "\\path\\"]
    assert [
        args[index + 1] for index, item in enumerate(args) if item == "--redact-value"
    ] == ["first value", "second value"]
    assert "--output-format" not in args
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_collection_inputs_keep_literal_values_and_do_not_gain_test_flags(
    adapter_process,
):
    run, calls = adapter_process
    valued = {
        "REQUEST_NAME_PATTERN": ("--request-name-pattern", r"^get\s+orders$"),
        "GLOBALS": ("--globals", "globals.json"),
        "DELAY_REQUEST": ("--delay-request", "0"),
        "ITERATION_COUNT": ("--iteration-count", "2"),
        "ITERATION_DATA": ("--iteration-data", "data with spaces.json"),
        "CAPTURE_RESPONSE_HEADERS": (
            "--capture-response-headers",
            "X-Request-ID, Server",
        ),
    }
    assert (
        run(
            **{key: value for key, (_, value) in valued.items()},
            ITEM="  req 'one'  , \\req\\two  ",
            ENV_VAR="FIRST=one%20value\n\nSECOND=a=b",
            KEEP_FILE="true",
            TEST_NAME_PATTERN="test only",
        )
        == 0
    )

    args = calls[0][0]
    for option, value in valued.values():
        assert args[args.index(option) + 1] == value
    assert [args[index + 1] for index, item in enumerate(args) if item == "--item"] == [
        "req 'one'",
        "\\req\\two",
    ]
    assert [
        args[index + 1] for index, item in enumerate(args) if item == "--env-var"
    ] == ["FIRST=one%20value", "SECOND=a=b"]
    assert "--keep-file" not in args
    assert "--test-name-pattern" not in args


def test_test_specific_inputs_do_not_gain_collection_flags(adapter_process):
    run, calls = adapter_process
    assert (
        run(
            COMMAND="test",
            TEST_NAME_PATTERN="literal test",
            KEEP_FILE="TRUE",
            ITEM="req_one",
            ENV_VAR="A=B",
            GLOBALS="globals",
            ITERATION_COUNT="2",
            CAPTURE_RESPONSE_HEADERS="Server",
        )
        == 0
    )

    args = calls[0][0]
    assert args[args.index("--test-name-pattern") + 1] == "literal test"
    assert "--keep-file" in args
    for option in (
        "--item",
        "--env-var",
        "--globals",
        "--iteration-count",
        "--capture-response-headers",
    ):
        assert option not in args


def test_real_cli_preserves_quotes_backslashes_and_interior_spaces(
    run_action, tmp_path
):
    captured = tmp_path / "args.json"
    result = run_action(
        ITEM="  req 'one'  , \\req\\two  ",
        DATA_FOLDERS="  dir 'one'  , \\dir\\two  ",
        TEST_ENV_FILE=str(captured),
    )

    assert result.returncode == 0, result.stderr
    args = json.loads(captured.read_text())["args"]
    assert [args[index + 1] for index, item in enumerate(args) if item == "--item"] == [
        "req 'one'",
        "\\req\\two",
    ]
    assert [
        args[index + 1] for index, item in enumerate(args) if item == "--dataFolders"
    ] == ["dir 'one'", "\\dir\\two"]


@pytest.mark.parametrize("output_format", ["", "json", "JSON"])
def test_convenience_json_is_opt_in_but_file_report_is_always_available(
    adapter_process, tmp_path, output_format
):
    run, _ = adapter_process
    assert run(OUTPUT_FORMAT=output_format) == 0
    outputs = read_outputs(tmp_path / "outputs")
    payload = Path(outputs["json-file"]).read_text()
    assert outputs["json-output"] == (payload if output_format else "")
    assert outputs["json-output-omitted"] == "false"


@pytest.mark.parametrize("character", ["a", "\u00e9", "\U0001f600"])
@pytest.mark.parametrize("extra_units", [0, 1])
def test_convenience_json_utf16_budget_keeps_complete_file_reports(
    adapter_process, tmp_path, character, extra_units
):
    run, _ = adapter_process
    report = {"plan_end": 0, "target_name": ""}
    base_units = len(json.dumps(report, ensure_ascii=False).encode("utf-16-le")) // 2
    units = len(character.encode("utf-16-le")) // 2
    report["target_name"] = character * ((32768 - base_units) // units)
    payload = json.dumps(report, ensure_ascii=False)
    if extra_units:
        report["target_name"] += character
        payload = json.dumps(report, ensure_ascii=False)
    too_large = len(payload.encode("utf-16-le")) > 65536

    assert run(payload=payload, OUTPUT_FORMAT="json") == 0

    outputs = read_outputs(tmp_path / "outputs")
    assert Path(outputs["json-file"]).read_text() == payload
    assert outputs["json-output-omitted"] == str(too_large).lower()
    assert outputs["json-output"] == ("" if too_large else payload)
    if not too_large:
        assert json.loads(outputs["json-output"]) == report


def test_hostile_identifier_is_a_literal_inso_argument(run_action, tmp_path):
    captured = tmp_path / "args.json"
    identifier = "orders $(touch SHOULD_NOT_EXIST); quoted 'name'"
    result = run_action(IDENTIFIER=identifier, TEST_ENV_FILE=str(captured))

    assert result.returncode == 0, result.stderr
    args = json.loads(captured.read_text())["args"]
    assert args[args.index("--") + 1 :] == [identifier]
    assert not (tmp_path / "SHOULD_NOT_EXIST").exists()


def test_unknown_request_counts_are_not_replaced_with_assertion_counts(
    adapter_process, tmp_path
):
    run, _ = adapter_process
    assert run() == 0
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["total"] == "1"
    assert outputs["requests"] == ""


def test_legacy_verbose_is_rejected_before_any_inso_execution(run_action, tmp_path):
    captured = tmp_path / "args.json"
    result = run_action(COMMAND="test", VERBOSE="true", TEST_ENV_FILE=str(captured))

    assert result.returncode == 0, result.stderr
    assert read_outputs(tmp_path / "outputs")["exit-code"] == "2"
    assert not captured.exists()
