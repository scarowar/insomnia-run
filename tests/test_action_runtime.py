"""Exercise the composite action shell against a controlled CLI process."""

import json
import os
from pathlib import Path
import re
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())
RUN_STEP = next(s for s in ACTION["runs"]["steps"] if s.get("id") == "run-cli")


@pytest.fixture
def run_action(tmp_path):
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    # Avoid writing Inso's package cache into the test operator's real home.
    mkdir = fake_bin / "mkdir"
    mkdir.write_text(
        '#!/bin/bash\nif [[ "$*" == "-p ${HOME}/.cache/pkg" ]]; then exit 0; fi\n'
        'exec /bin/mkdir "$@"\n'
    )
    mkdir.chmod(0o755)
    cli = tmp_path / "insomnia-run-venv" / "bin" / "insomnia-run"
    cli.parent.mkdir(parents=True)
    cli.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "if os.environ.get('TEST_ENV_FILE'):\n"
        "    pathlib.Path(os.environ['TEST_ENV_FILE']).write_text(json.dumps({'proxy': os.environ.get('HTTPS_PROXY'), 'args': sys.argv}))\n"
        "print('## Insomnia report\\n\\n- result')\n"
        "if '--junit-output' in sys.argv and not os.environ.get('TEST_SKIP_JUNIT'):\n"
        "    path = pathlib.Path(sys.argv[sys.argv.index('--junit-output') + 1])\n"
        "    path.parent.mkdir(parents=True, exist_ok=True)\n"
        "    path.write_text('<testsuite tests=\"1\" />')\n"
        "if '--output-format' in sys.argv:\n"
        "    print(os.environ.get('TEST_JSON', json.dumps({'results': []})), file=sys.stderr)\n"
        "sys.exit(int(os.environ.get('TEST_CLI_EXIT', '0')))\n"
    )
    cli.chmod(0o755)

    def run(**overrides):
        env = os.environ.copy()
        for key, value in RUN_STEP["env"].items():
            match = re.fullmatch(r"\$\{\{ inputs\.([\w-]+) \}\}", value)
            env[key] = ACTION["inputs"][match[1]].get("default", "") if match else ""
        env.update(
            RUNNER_TEMP=str(tmp_path),
            COMMAND="collection",
            WORKING_DIR="fixture.yaml",
            PATH=f"{fake_bin}:{os.environ['PATH']}",
            GITHUB_SERVER_URL="https://github.com",
            GITHUB_OUTPUT=str(tmp_path / "outputs"),
            GITHUB_STEP_SUMMARY=str(tmp_path / "summary"),
        )
        env.update(overrides)
        return subprocess.run(
            ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", RUN_STEP["run"]],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

    return run


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


@pytest.mark.parametrize("command", ["collection", "test"])
@pytest.mark.parametrize("cli_exit", ["0", "1"])
def test_action_preserves_cli_exit_and_reports(run_action, tmp_path, command, cli_exit):
    result = run_action(COMMAND=command, OUTPUT_FORMAT="json", TEST_CLI_EXIT=cli_exit)

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["exit-code"] == cli_exit
    assert json.loads(outputs["json-output"]) == {"results": []}
    assert Path(outputs["junit-file"]).exists()
    reports = Path(outputs["report-directory"])
    assert (reports / "report.md").read_text() == (tmp_path / "summary").read_text()
    assert json.loads((reports / "report.json").read_text()) == {"results": []}
    assert (reports / "junit.xml").exists()


@pytest.mark.parametrize("failed_file", ["GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"])
def test_action_fails_when_publishing_reports_fails(run_action, tmp_path, failed_file):
    result = run_action(**{failed_file: str(tmp_path)})

    assert result.returncode != 0


def test_action_does_not_publish_cli_diagnostics_as_json(run_action, tmp_path):
    result = run_action(
        OUTPUT_FORMAT="json", TEST_JSON="invalid options", TEST_CLI_EXIT="2"
    )

    assert result.returncode == 0, result.stderr
    outputs = read_outputs(tmp_path / "outputs")
    assert outputs["exit-code"] == "2"
    assert "json-output" not in outputs
    assert "invalid options" in outputs["markdown"]


def test_action_does_not_reuse_stale_junit_reports(run_action, tmp_path):
    first = run_action()
    assert first.returncode == 0, first.stderr
    second = run_action(TEST_SKIP_JUNIT="true", TEST_CLI_EXIT="2")
    assert second.returncode == 0, second.stderr
    assert read_outputs(tmp_path / "outputs")["junit-file"] == ""


@pytest.mark.parametrize("days", ["0", "401", "invalid"])
def test_artifact_retention_is_validated(run_action, days):
    result = run_action(UPLOAD_ARTIFACT="true", ARTIFACT_RETENTION_DAYS=days)

    assert result.returncode != 0
    assert "artifact-retention-days" in result.stdout


def test_builtin_artifact_upload_fails_clearly_on_ghes(run_action):
    result = run_action(
        UPLOAD_ARTIFACT="true", GITHUB_SERVER_URL="https://github.example.test"
    )

    assert result.returncode != 0
    assert "require GitHub.com" in result.stdout


def test_inherited_enterprise_proxy_is_not_erased(run_action, tmp_path):
    captured = tmp_path / "env.json"
    result = run_action(
        HTTPS_PROXY="http://enterprise.proxy:8080",
        INPUT_HTTPS_PROXY="http://override.proxy:8080",
        TEST_ENV_FILE=str(captured),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(captured.read_text())
    assert payload["proxy"] == "http://enterprise.proxy:8080"
    assert (
        payload["args"][payload["args"].index("--https-proxy") + 1]
        == "http://override.proxy:8080"
    )
