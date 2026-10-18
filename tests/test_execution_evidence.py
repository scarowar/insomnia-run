import json
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired

import pytest

from insomnia_run.models import InsoCollectionOptions, InsoTestOptions
from insomnia_run.runner import InsoRunner


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(InsoRunner, "_supports_native_report", lambda self: True)
    return InsoRunner()


def native_command(monkeypatch, payload, code=0, stdout=""):
    def run(cmd, timeout):
        Path(cmd[cmd.index("--output") + 1]).write_text(json.dumps(payload))
        return CompletedProcess(cmd, code, stdout, "")

    monkeypatch.setattr(InsoRunner, "_run_command", staticmethod(run))


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
