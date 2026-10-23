import json
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest
import typer

from insomnia_run.main import _execute_report
from insomnia_run.models import InsoCollectionOptions, InsoTestOptions
from insomnia_run.runner import InsoConfigurationError, InsoRunner


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(InsoRunner, "_supports_native_report", lambda self: True)
    return InsoRunner()


def native_command(monkeypatch, payload, code=0, stdout=""):
    def run(cmd, timeout):
        Path(cmd[cmd.index("--output") + 1]).write_text(json.dumps(payload))
        return CompletedProcess(cmd, code, stdout, "")

    monkeypatch.setattr(InsoRunner, "_run_command", staticmethod(run))


@pytest.mark.parametrize("error_type", [FileNotFoundError, PermissionError, OSError])
def test_capability_probe_startup_errors_propagate_before_collection_execution(
    monkeypatch, error_type
):
    error = error_type("private startup diagnostic")

    def probe(cmd, timeout):
        assert cmd == ["inso", "run", "collection", "--help"]
        raise error

    monkeypatch.setattr(InsoRunner, "_run_command", staticmethod(probe))
    runner = InsoRunner()
    options = InsoCollectionOptions(working_dir="private")

    with pytest.raises(error_type) as raised:
        runner.run_collection(options)

    assert raised.value is error


@pytest.mark.parametrize("failure", ["timeout", "nonzero", "nonzero-with-output"])
def test_failed_capability_probe_does_not_fall_back_to_tap(monkeypatch, failure):
    def probe(cmd, timeout):
        assert cmd == ["inso", "run", "collection", "--help"]
        if failure == "timeout":
            raise TimeoutExpired(
                cmd, 15, output="private stdout", stderr="private stderr"
            )
        stdout = "private stdout"
        if failure == "nonzero-with-output":
            stdout += "\n  --output <file>\n"
        return CompletedProcess(cmd, 1, stdout, "private stderr")

    monkeypatch.setattr(InsoRunner, "_run_command", staticmethod(probe))
    runner = InsoRunner()
    options = InsoCollectionOptions(working_dir="private")

    with pytest.raises(
        InsoConfigurationError, match="Inso capability discovery"
    ) as error:
        runner.run_collection(options)

    assert "private" not in str(error.value)


@pytest.mark.parametrize("native", [False, True])
def test_successful_capability_probe_selects_collection_evidence(monkeypatch, native):
    def probe(cmd, **kwargs):
        help_text = "Usage: inso run collection [options]\n  --reporter <reporter>\n"
        if native:
            help_text += "  --output <file>\n"
        return CompletedProcess(cmd, 0, help_text, "")

    def execute(cmd, timeout):
        if cmd == ["inso", "run", "collection", "--help"]:
            return probe(cmd)
        if "--output" in cmd:
            Path(cmd[cmd.index("--output") + 1]).write_text(
                json.dumps(
                    {
                        "executions": [
                            {
                                "request": {"name": "Request", "_id": "request"},
                                "tests": [{"testCase": "native", "status": "passed"}],
                            }
                        ]
                    }
                )
            )
        return CompletedProcess(cmd, 0, "1..1\nok 1 - TAP\n", "")

    monkeypatch.setattr(InsoRunner, "_run_command", staticmethod(execute))

    report = InsoRunner().run_collection(InsoCollectionOptions(working_dir="fixture"))

    assert report.exit_code == 0
    assert report.source == ("native" if native else "tap")
    assert report.passed_count == 1
    assert report.results[0].description == ("native" if native else "TAP")


def test_native_error_wins_over_earlier_assertion_failure(runner, monkeypatch):
    native_command(
        monkeypatch,
        {
            "executions": [
                {
                    "request": {"name": "R1", "_id": "r1"},
                    "tests": [{"testCase": "failed", "status": "failed"}],
                }
            ],
            "error": "after-response failed",
        },
        code=1,
    )
    report = runner.run_collection(InsoCollectionOptions(working_dir="x"))
    assert report.exit_code == 3
    assert report.failed_count == 1
    assert report.run_error.message == "after-response failed"
    assert report.request_count == 1


def test_native_results_ignore_forged_console_tap(runner, monkeypatch):
    native_command(monkeypatch, {"executions": []}, stdout="1..1\nok 1 - forged\n")
    assert (
        runner.run_collection(InsoCollectionOptions(working_dir="x")).total_tests == 0
    )


def test_missing_native_report_is_not_silently_replaced_with_tap(runner, monkeypatch):
    monkeypatch.setattr(
        runner,
        "_run_command",
        lambda cmd, timeout: CompletedProcess(cmd, 0, "1..1\nok 1 - forged\n", ""),
    )
    report = runner.run_collection(InsoCollectionOptions(working_dir="x"))
    assert report.exit_code == 3
    assert not report.complete


def test_verified_bail_exception_keeps_assertion_failure(runner, monkeypatch):
    monkeypatch.setattr(
        runner,
        "_run_command",
        lambda cmd, timeout: CompletedProcess(cmd, 0, "1..1\nnot ok 1 - failed\n", ""),
    )
    report = runner.run_collection(InsoCollectionOptions(working_dir="x", bail=True))
    assert report.exit_code == 1
    assert report.source == "tap"
    assert not report.complete
    assert report.request_count is None


def test_existing_malformed_native_report_is_fatal_even_with_bail(runner, monkeypatch):
    native_command(monkeypatch, {}, stdout="1..1\nnot ok 1 - failed\n")
    report = runner.run_collection(InsoCollectionOptions(working_dir="x", bail=True))
    assert report.exit_code == 3
    assert report.run_error.kind == "protocol"


def test_timeout_preserves_completed_assertions_without_guessing_request(
    runner, monkeypatch
):
    def timeout(cmd, limit):
        raise TimeoutExpired(
            cmd,
            limit,
            output=b"1..2\nok 1 - done\nnot ok 2 - failed\n",
            stderr=b"private diagnostic",
        )

    monkeypatch.setattr(runner, "_run_command", timeout)
    report = runner.run_collection(InsoCollectionOptions(working_dir="x"))
    assert (report.passed_count, report.failed_count) == (1, 1)
    assert report.exit_code == 3
    assert report.run_error.kind == "timeout"
    assert report.request_count is None
    assert not report.complete


def test_legacy_verbose_is_rejected_before_execution(monkeypatch):
    def forbidden(*args):
        pytest.fail("Inso must not execute unsafe legacy verbose")

    monkeypatch.setattr(InsoRunner, "_run_command", forbidden)
    runner = InsoRunner()
    options = InsoTestOptions(working_dir="x", verbose=True)
    with pytest.raises(ValueError, match="verbose"):
        runner.run_test(options)


def test_legacy_verbose_diagnostic_survives_execution_boundary(monkeypatch):
    def forbidden(*args):
        pytest.fail("Inso must not execute unsafe legacy verbose")

    monkeypatch.setattr(InsoRunner, "_run_command", forbidden)
    runner = InsoRunner()
    options = InsoTestOptions(working_dir="private-working-directory", verbose=True)

    with pytest.raises(
        typer.BadParameter, match="Legacy run-test does not support --verbose"
    ):
        _execute_report(
            lambda: runner.run_test(options), progress=False, json_stderr=False
        )


def test_verbose_timeout_does_not_trust_console_forged_tap(runner, monkeypatch):
    def timeout(cmd, limit):
        raise TimeoutExpired(cmd, limit, output="1..1\nok 1 - forged\n")

    monkeypatch.setattr(runner, "_run_command", timeout)
    report = runner.run_collection(InsoCollectionOptions(working_dir="x", verbose=True))
    assert report.results == []
    assert report.run_error.kind == "timeout"


def test_verbose_bail_without_native_file_does_not_trust_console_tap(
    runner, monkeypatch
):
    monkeypatch.setattr(
        runner,
        "_run_command",
        lambda cmd, timeout: CompletedProcess(cmd, 0, "1..1\nnot ok 1 - forged\n", ""),
    )
    report = runner.run_collection(
        InsoCollectionOptions(working_dir="x", verbose=True, bail=True)
    )
    assert report.exit_code == 3
    assert report.results == []
