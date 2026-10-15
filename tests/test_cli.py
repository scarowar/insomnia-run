import json
from unittest.mock import patch
from xml.etree import ElementTree

import pytest
from typer.testing import CliRunner

from insomnia_run.main import app
from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus


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

    assert result.exit_code != 0
    assert isinstance(result.exception, OSError)
