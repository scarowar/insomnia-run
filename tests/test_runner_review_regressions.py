import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qsl

import pytest

from insomnia_run.models import InsoCollectionOptions
from insomnia_run.runner import InsoRunner
from insomnia_run.privacy import Redactor


def test_inso_child_cannot_read_action_or_oidc_credentials(monkeypatch):
    private = {
        "REDACT_VALUES": "private-redactions",
        "ENV_VAR": "TOKEN=private",
        "INPUT_TOKEN": "private-input",
        "ACTION_COMMENT_TOKEN": "private-comment",
        "INSOMNIA_RUN_INTERNAL": "private-internal",
        "GITHUB_TOKEN": "private-github",
        "GH_TOKEN": "private-gh",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "private-oidc",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://oidc.invalid",
    }
    for key, value in private.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("COLLECTION_API_TOKEN", "caller-authorized")
    result = InsoRunner._run_command(
        [sys.executable, "-c", "import json, os; print(json.dumps(dict(os.environ)))"],
        10,
    )
    inherited = json.loads(result.stdout)
    leaked_keys = sorted(private.keys() & inherited.keys())
    assert leaked_keys == []
    assert inherited["COLLECTION_API_TOKEN"] == "caller-authorized"
    assert inherited["INSO_TELEMETRY_DISABLED"] == "1"
    assert all(os.environ[key] == value for key, value in private.items())


@pytest.mark.parametrize("partial", ["", '{"executions": ['])
def test_timeout_recovers_tap_when_native_file_is_truncated(monkeypatch, partial):
    monkeypatch.setattr(InsoRunner, "_supports_native_report", lambda self: True)

    def execute(cmd, timeout):
        Path(cmd[cmd.index("--output") + 1]).write_text(partial)
        raise subprocess.TimeoutExpired(cmd, timeout, output="1..2\nok 1 - completed\n")

    monkeypatch.setattr(InsoRunner, "_run_command", staticmethod(execute))
    report = InsoRunner().run_collection(InsoCollectionOptions(working_dir="fixture"))
    assert report.passed_count == 1
    assert report.results[0].description == "completed"
    assert report.run_error.kind == "timeout"
    assert not report.complete


def test_missing_native_report_preserves_tap_bailout(monkeypatch):
    monkeypatch.setattr(InsoRunner, "_supports_native_report", lambda self: True)
    monkeypatch.setattr(
        InsoRunner,
        "_run_command",
        staticmethod(
            lambda cmd, timeout: subprocess.CompletedProcess(
                cmd, 1, "Bail out! service unavailable\n", ""
            )
        ),
    )
    report = InsoRunner().run_collection(InsoCollectionOptions(working_dir="fixture"))
    assert report.run_error.message == "Inso CLI Error: TAP bailout."


def test_mapping_env_vars_preserve_urlsearchparams_values():
    values = {"TOKEN": "a+b&c=d /?", "SPACE KEY": "é"}
    cmd = []
    InsoRunner._apply_collection_options(
        cmd, InsoCollectionOptions(working_dir="fixture", env_var=values)
    )
    forwarded = [cmd[i + 1] for i, value in enumerate(cmd) if value == "--env-var"]
    assert dict(pair for item in forwarded for pair in parse_qsl(item)) == values


def test_large_diagnostics_do_not_drop_assertions_before_publication(monkeypatch):
    stdout = "1..1\nok 1 - completed\n" + "# é\n" * 300_000
    monkeypatch.setattr(InsoRunner, "_supports_native_report", lambda self: False)
    monkeypatch.setattr(
        InsoRunner,
        "_run_command",
        staticmethod(
            lambda cmd, timeout: subprocess.CompletedProcess(
                cmd, 0, stdout, "last diagnostic\n"
            )
        ),
    )
    report = InsoRunner().run_collection(InsoCollectionOptions(working_dir="fixture"))
    assert report.passed_count == 1
    assert report.raw_output.endswith("last diagnostic\n")


def test_execution_error_includes_redacted_stderr_without_raw_publication(monkeypatch):
    monkeypatch.setattr(InsoRunner, "_supports_native_report", lambda self: False)
    monkeypatch.setattr(
        InsoRunner,
        "_run_command",
        staticmethod(
            lambda cmd, timeout: subprocess.CompletedProcess(
                cmd,
                23,
                "1..1\nok 1 - completed\n",
                "Cannot connect to the selected server\nGITHUB_TOKEN=private-token\ninline-private-value\n",
            )
        ),
    )
    report = InsoRunner(redactor=Redactor(["inline-private-value"])).run_collection(
        InsoCollectionOptions(working_dir="fixture")
    )
    assert report.run_error.kind == "execution"
    assert "code 23" in report.run_error.message
    assert "Cannot connect" in report.run_error.message
    assert "private-token" not in report.run_error.message
    assert "inline-private-value" not in report.run_error.message


def test_execution_error_keeps_only_the_last_six_nonempty_diagnostics(monkeypatch):
    monkeypatch.setattr(InsoRunner, "_supports_native_report", lambda self: False)
    stderr = "\n\n".join(f"diagnostic {index}" for index in range(10))
    monkeypatch.setattr(
        InsoRunner,
        "_run_command",
        staticmethod(
            lambda cmd, timeout: subprocess.CompletedProcess(cmd, 23, "1..0\n", stderr)
        ),
    )
    report = InsoRunner().run_collection(InsoCollectionOptions(working_dir="fixture"))
    assert report.run_error.message.endswith(
        "\n".join(f"diagnostic {index}" for index in range(4, 10))
    )
    assert "diagnostic 3" not in report.run_error.message
