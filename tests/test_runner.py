import pytest
from contextlib import contextmanager
import json
import os
import signal
from subprocess import TimeoutExpired
import sys
from types import SimpleNamespace
from unittest.mock import patch
from insomnia_run.runner import InsoRunner
from insomnia_run.models import InsoCollectionOptions, InsoTestOptions, RunType


@contextmanager
def inso_output(stdout, stderr="", returncode=0):
    with (
        patch("insomnia_run.runner.subprocess.Popen") as popen,
        patch.object(InsoRunner, "_supports_native_report", return_value=False),
        patch("insomnia_run.runner.os.killpg"),
    ):
        process = popen.return_value.__enter__.return_value

        def communicate(**kwargs):
            for key, value in (("stdout", stdout), ("stderr", stderr)):
                stream = popen.call_args.kwargs[key]
                stream.write(value.encode("utf-8"))
                stream.flush()
            return None, None

        process.communicate.side_effect = communicate
        process.pid = 12345
        process.returncode = returncode
        yield popen


@pytest.mark.parametrize(
    "method,options_type",
    [("run_collection", InsoCollectionOptions), ("run_test", InsoTestOptions)],
)
@pytest.mark.parametrize("parent_setting", [None, "", "0", "parent-value", "1"])
def test_real_inso_child_disables_telemetry_without_changing_parent(
    tmp_path, monkeypatch, method, options_type, parent_setting
):
    inso = tmp_path / "inso"
    inso.write_text(
        f"#!{sys.executable}\n"
        "import json, os\n"
        "print(json.dumps({\n"
        "    'telemetry': os.environ.get('INSO_TELEMETRY_DISABLED'),\n"
        "    'inherited': os.environ.get('INHERITED_CHILD_SENTINEL'),\n"
        "}))\n"
        "print('1..1\\nok 1 - passes')\n"
    )
    inso.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("INHERITED_CHILD_SENTINEL", "keep-this-value")
    if parent_setting is None:
        monkeypatch.delenv("INSO_TELEMETRY_DISABLED", raising=False)
    else:
        monkeypatch.setenv("INSO_TELEMETRY_DISABLED", parent_setting)
    parent_environment = dict(os.environ)

    report = getattr(InsoRunner(), method)(options_type(working_dir="fixture"))

    assert report.passed_count == 1
    assert report.failed_count == 0
    assert json.loads(report.raw_output.splitlines()[0]) == {
        "telemetry": "1",
        "inherited": None,
    }
    assert dict(os.environ) == parent_environment


def test_interruption_terminates_the_inso_process_group():
    with inso_output("") as popen, patch("insomnia_run.runner.os.killpg") as kill_group:
        process = popen.return_value.__enter__.return_value
        process.pid = 12345
        process.communicate.side_effect = [KeyboardInterrupt(), ("", "")]

        with pytest.raises(KeyboardInterrupt):
            InsoRunner._run_command(["inso", "run", "test"], 5)

        kill_group.assert_called_once_with(12345, signal.SIGKILL)


def test_non_posix_execution_is_rejected_before_launch():
    with (
        inso_output("") as popen,
        patch("insomnia_run.runner.os", SimpleNamespace(name="nt")),
    ):
        with pytest.raises(NotImplementedError, match="POSIX"):
            InsoRunner._run_command(["inso", "run", "test"], 5)

        popen.assert_not_called()


@pytest.mark.parametrize("failure", ["group", "kill", "drain", "drain_timeout"])
def test_cleanup_os_errors_do_not_replace_an_interrupt(failure):
    with (
        inso_output("") as popen,
        patch(
            "insomnia_run.runner.os.killpg",
            side_effect=PermissionError() if failure in {"group", "kill"} else None,
        ),
    ):
        process = popen.return_value.__enter__.return_value
        drain_result = ("", "")
        if failure == "drain":
            drain_result = OSError()
        elif failure == "drain_timeout":
            drain_result = TimeoutExpired(cmd="inso", timeout=1)
        process.communicate.side_effect = [KeyboardInterrupt(), drain_result]
        if failure == "kill":
            process.kill.side_effect = OSError()

        with pytest.raises(KeyboardInterrupt):
            InsoRunner._run_command(["inso", "run", "test"], 5)

        if failure in {"group", "kill"}:
            process.kill.assert_called_once()


class TestInsoRunnerCollection:
    @pytest.fixture
    def runner(self):
        return InsoRunner()

    @pytest.fixture
    def mock_subprocess(self):
        with inso_output("""TAP version 13
1..1
ok 1 - Test passed
""") as popen:
            yield popen

    def test_minimal_collection_command(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path/to/insomnia")
        runner.run_collection(options)

        mock_subprocess.assert_called_once()
        cmd = mock_subprocess.call_args[0][0]

        assert cmd[:3] == ["inso", "run", "collection"]
        assert "-w" in cmd
        assert "/path/to/insomnia" in cmd
        assert "--reporter" in cmd
        assert "tap" in cmd
        assert "--ci" in cmd

    def test_collection_with_identifier(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path", identifier="My Collection")
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "My Collection" in cmd
        assert cmd[-2:] == ["--", "My Collection"]

    def test_collection_with_environment(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path", environment="Production")
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--env" in cmd
        env_idx = cmd.index("--env")
        assert cmd[env_idx + 1] == "Production"

    def test_collection_with_request_pattern(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path", request_name_pattern=".*login.*"
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--requestNamePattern" in cmd
        idx = cmd.index("--requestNamePattern")
        assert cmd[idx + 1] == ".*login.*"

    def test_collection_with_multiple_items(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path", item=["req_001", "req_002", "req_003"]
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        item_count = cmd.count("--item")
        assert item_count == 3

    def test_collection_with_env_vars(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path", env_var={"API_KEY": "secret", "TOKEN": "abc123"}
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--env-var" in cmd
        assert "API_KEY=secret" in cmd
        assert "TOKEN=abc123" in cmd

    def test_env_var_occurrences_are_forwarded_without_collapsing_keys(
        self, runner, mock_subprocess
    ):
        runner.run_collection(
            InsoCollectionOptions(
                working_dir="/path", env_var=["A=old&B=keep", "A=new"]
            )
        )
        cmd = mock_subprocess.call_args[0][0]

        assert [cmd[i + 1] for i, value in enumerate(cmd) if value == "--env-var"] == [
            "A=old&B=keep",
            "A=new",
        ]

    def test_collection_with_timeouts(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path", delay_request=500, request_timeout=30000
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--delay-request" in cmd
        assert "500" in cmd
        assert "--requestTimeout" in cmd
        assert "30000" in cmd

    def test_explicit_zero_timeouts_and_delays_are_forwarded(
        self, runner, mock_subprocess
    ):
        runner.run_collection(
            InsoCollectionOptions(
                working_dir="/path", delay_request=0, request_timeout=0
            )
        )
        cmd = mock_subprocess.call_args[0][0]

        assert cmd[cmd.index("--delay-request") + 1] == "0"
        assert cmd[cmd.index("--requestTimeout") + 1] == "0"

    @pytest.mark.parametrize(
        "identifier", ["--help", "--version", "-k", "name with spaces"]
    )
    def test_identifier_is_positional_after_all_options(
        self, runner, mock_subprocess, identifier
    ):
        runner.run_collection(
            InsoCollectionOptions(working_dir="/path", identifier=identifier, bail=True)
        )
        cmd = mock_subprocess.call_args[0][0]

        assert cmd[-2:] == ["--", identifier]
        assert cmd.index("--bail") < cmd.index("--")

    def test_collection_with_iteration_options(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path", iteration_count=5, iteration_data="/data/test.csv"
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--iteration-count" in cmd
        assert "5" in cmd
        assert "--iteration-data" in cmd
        assert "/data/test.csv" in cmd

    def test_collection_with_bail(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path", bail=True)
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--bail" in cmd

    def test_collection_with_ssl_disabled(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path", disable_cert_validation=True
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--disableCertValidation" in cmd

    def test_collection_with_proxies(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            https_proxy="https://proxy:8080",
            http_proxy="https://proxy:8080",
            no_proxy="localhost,127.0.0.1",
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--httpsProxy" in cmd
        assert "https://proxy:8080" in cmd
        assert "--httpProxy" in cmd
        assert "https://proxy:8080" in cmd
        assert "--noProxy" in cmd
        assert "localhost,127.0.0.1" in cmd

    def test_collection_with_data_folders(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path", data_folders=["./data", "/home/user/data"]
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        folder_count = cmd.count("--dataFolders")
        assert folder_count == 2

    def test_collection_with_verbose(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path", verbose=True)
        with pytest.raises(ValueError, match="Native collection reporting"):
            runner.run_collection(options)
        mock_subprocess.assert_not_called()

    def test_collection_report_type(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path")
        report = runner.run_collection(options)

        assert report.run_type == RunType.COLLECTION

    def test_collection_with_execution_timeout(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path", execution_timeout=123)
        runner.run_collection(options)
        mock_subprocess.assert_called_once()
        process = mock_subprocess.return_value.__enter__.return_value
        process.communicate.assert_called_once_with(timeout=123)

    @pytest.mark.parametrize("group_gone", [False, True])
    def test_collection_timeout_error_message(self, runner, group_gone):
        with (
            inso_output("") as popen,
            patch(
                "insomnia_run.runner.os.killpg",
                side_effect=ProcessLookupError() if group_gone else None,
            ),
        ):
            process = popen.return_value.__enter__.return_value
            process.communicate.side_effect = [
                TimeoutExpired(cmd="inso", timeout=77),
                ("", ""),
            ]
            options = InsoCollectionOptions(working_dir="/path", execution_timeout=77)
            report = runner.run_collection(options)
            assert report.total_tests == 0
            assert report.exit_code == 3
            assert f"{options.execution_timeout}" in report.run_error.message

    def test_collection_cli_error_from_stdout_is_reported(self, runner):
        with inso_output(
            "Error: No data source found at path '/tmp/missing'\nTIP: use --workingDir",
            returncode=1,
        ):
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))

        assert report.exit_code == 3
        assert "No data source found" in report.raw_output
        assert "No data source found" not in report.run_error.message
        assert "TIP:" not in report.run_error.message

    def test_collection_nonzero_exit_with_tap_results_still_fails(self, runner):
        with inso_output("TAP version 13\n1..1\nok 1 - Passed\n", returncode=1):
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))

        assert report.passed_count == 1
        assert report.failed_count == 0
        assert report.exit_code == 3
        assert "code 1" in report.run_error.message

    def test_collection_cli_error_preserves_both_streams_only_in_raw_output(
        self, runner
    ):
        with inso_output(
            "Error: No data source found at path '/tmp/missing'",
            "Warning: using default configuration",
            returncode=1,
        ):
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))

        assert report.exit_code == 3
        assert "No data source found" in report.raw_output
        assert "Warning: using default configuration" in report.raw_output
        assert all("/tmp/missing" not in r.description for r in report.results)


class TestInsoRunnerTest:
    @pytest.fixture
    def runner(self):
        return InsoRunner()

    @pytest.fixture
    def mock_subprocess(self):
        with inso_output("""ok 1 Test Suite Test Name
# tests 1
# pass 1
1..1
""") as popen:
            yield popen

    def test_minimal_test_command(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path/to/insomnia")
        runner.run_test(options)

        mock_subprocess.assert_called_once()
        cmd = mock_subprocess.call_args[0][0]

        assert cmd[:3] == ["inso", "run", "test"]
        assert "-w" in cmd
        assert "/path/to/insomnia" in cmd
        assert "--reporter" in cmd
        assert "tap" in cmd
        assert "--ci" in cmd

    def test_test_with_identifier(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path", identifier="My Test Suite")
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "My Test Suite" in cmd

    @pytest.mark.parametrize(
        "identifier", ["--help", "--version", "-k", "name with spaces"]
    )
    def test_identifier_is_positional_after_all_options(
        self, runner, mock_subprocess, identifier
    ):
        runner.run_test(
            InsoTestOptions(working_dir="/path", identifier=identifier, keep_file=True)
        )
        cmd = mock_subprocess.call_args[0][0]

        assert cmd[-2:] == ["--", identifier]
        assert cmd.index("--keepFile") < cmd.index("--")

    def test_explicit_zero_request_timeout_is_forwarded(self, runner, mock_subprocess):
        runner.run_test(InsoTestOptions(working_dir="/path", request_timeout=0))
        cmd = mock_subprocess.call_args[0][0]

        assert cmd[cmd.index("--requestTimeout") + 1] == "0"

    def test_test_with_name_pattern(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path", test_name_pattern=".*auth.*")
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--testNamePattern" in cmd
        idx = cmd.index("--testNamePattern")
        assert cmd[idx + 1] == ".*auth.*"

    def test_test_with_bail(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path", bail=True)
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--bail" in cmd

    def test_test_with_keep_file(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path", keep_file=True)
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--keepFile" in cmd

    def test_test_with_timeout(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path", request_timeout=60000)
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--requestTimeout" in cmd
        assert "60000" in cmd

    def test_test_with_ssl_disabled(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path", disable_cert_validation=True)
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--disableCertValidation" in cmd

    def test_test_with_proxies(self, runner, mock_subprocess):
        options = InsoTestOptions(
            working_dir="/path",
            https_proxy="https://proxy:8080",
            http_proxy="https://proxy:8080",
            no_proxy="localhost",
        )
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--httpsProxy" in cmd
        assert "--httpProxy" in cmd
        assert "--noProxy" in cmd

    def test_test_report_type(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path")
        report = runner.run_test(options)

        assert report.run_type == RunType.TEST

    def test_test_target_name_set(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path", identifier="Auth Tests")
        report = runner.run_test(options)

        assert report.target_name == "Auth Tests"

    def test_test_with_execution_timeout(self, runner, mock_subprocess):
        options = InsoTestOptions(working_dir="/path", execution_timeout=456)
        runner.run_test(options)
        mock_subprocess.assert_called_once()
        process = mock_subprocess.return_value.__enter__.return_value
        process.communicate.assert_called_once_with(timeout=456)

    def test_test_timeout_error_message(self, runner):
        with inso_output("") as popen, patch("insomnia_run.runner.os.killpg"):
            process = popen.return_value.__enter__.return_value
            process.communicate.side_effect = [
                TimeoutExpired(cmd="inso", timeout=88),
                ("", ""),
            ]
            options = InsoTestOptions(working_dir="/path", execution_timeout=88)
            report = runner.run_test(options)
            assert report.total_tests == 0
            assert report.exit_code == 3
            assert f"{options.execution_timeout}" in report.run_error.message

    def test_test_cli_error_from_stdout_is_reported(self, runner):
        with inso_output("No test suites found; cannot run tests.", returncode=1):
            report = runner.run_test(InsoTestOptions(working_dir="/path"))

        assert report.exit_code == 3
        assert "No test suites found" in report.raw_output
        assert "No test suites found" not in report.run_error.message
