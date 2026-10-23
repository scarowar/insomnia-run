import json
import subprocess
import sys

import pytest

from insomnia_run import action_runtime
from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus
from insomnia_run.runner import InsoRunner


@pytest.fixture
def env(tmp_path, monkeypatch):
    values = {
        "COMMAND": "collection",
        "WORKING_DIR": "fixture",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_WORKSPACE": str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def test_action_runs_in_process_and_keeps_annotations_with_json(
    env, monkeypatch, capfd
):
    env.update(
        OUTPUT_FORMAT="json",
        REDACT_VALUES="private-value",
        ANNOTATIONS="true",
        PROGRESS="true",
    )
    monkeypatch.setattr(
        InsoRunner,
        "run_collection",
        lambda self, options: InsoRunReport(
            plan_end=1,
            results=[
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="failure",
                    message="private-value",
                )
            ],
        ),
    )

    def reject_python_child(cmd, **kwargs):
        pytest.fail(
            "Action execution must not put redaction values on a Python subprocess command line"
        )

    monkeypatch.setattr(subprocess, "run", reject_python_child)
    assert action_runtime.run_action(env) == 0
    captured = capfd.readouterr()
    assert "::error " in captured.err
    assert "Starting Inso execution." in captured.err
    assert "private-value" not in captured.out + captured.err
    assert sys.argv.count("private-value") == 0


@pytest.mark.parametrize(
    "variable",
    [
        "BAIL",
        "VERBOSE",
        "JUNIT_REPORT",
        "PROGRESS",
        "ANNOTATIONS",
        "UPLOAD_ARTIFACT",
        "INCLUDE_RAW_OUTPUT",
        "KEEP_FILE",
        "DISABLE_CERT_VALIDATION",
    ],
)
def test_invalid_boolean_is_rejected_before_execution(env, monkeypatch, variable):
    env[variable] = "yes"
    monkeypatch.setattr(
        InsoRunner, "run_collection", lambda *args: pytest.fail("Inso ran")
    )
    assert action_runtime.run_action(env) == 2


@pytest.mark.parametrize(
    "variable",
    [
        "ENV_VAR",
        "ITEM",
        "GLOBALS",
        "ITERATION_COUNT",
        "ITERATION_DATA",
        "DELAY_REQUEST",
        "REQUEST_NAME_PATTERN",
        "CAPTURE_RESPONSE_HEADERS",
    ],
)
def test_test_command_rejects_collection_inputs(env, variable):
    env.update(COMMAND="test")
    env[variable] = "1"
    assert action_runtime.run_action(env) == 2


@pytest.mark.parametrize(
    "variable,value", [("TEST_NAME_PATTERN", "name"), ("KEEP_FILE", "true")]
)
def test_collection_command_rejects_test_inputs(env, variable, value):
    env[variable] = value
    assert action_runtime.run_action(env) == 2


def test_complete_is_a_published_action_output(env, monkeypatch, tmp_path):
    monkeypatch.setattr(
        InsoRunner,
        "run_collection",
        lambda self, options: InsoRunReport(plan_end=0, complete=False),
    )
    assert action_runtime.run_action(env) == 0
    # Outputs use randomized heredoc delimiters; the value follows its key.
    lines = (tmp_path / "outputs").read_text().splitlines()
    assert any(
        line.startswith("complete<<") and lines[index + 1] == "false"
        for index, line in enumerate(lines)
    )
    reports = list(tmp_path.glob("insomnia-run-reports.*/report.json"))
    assert json.loads(reports[0].read_text())["complete"] is False
