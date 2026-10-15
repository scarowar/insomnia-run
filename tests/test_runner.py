import pytest
from contextlib import contextmanager
import signal
from subprocess import TimeoutExpired
from types import SimpleNamespace
from unittest.mock import patch
from insomnia_run.runner import InsoRunner
from insomnia_run.models import InsoCollectionOptions, InsoTestOptions, RunType


@contextmanager
def inso_output(stdout, stderr="", returncode=0):
    with patch("insomnia_run.runner.subprocess.Popen") as popen:
        process = popen.return_value.__enter__.return_value
        process.communicate.return_value = (stdout, stderr)
        process.returncode = returncode
        yield popen


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
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--verbose" in cmd

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
            assert report.plan_end == report.total_tests == 1
            assert f"{options.execution_timeout}" in report.raw_output
            assert any(
                f"{options.execution_timeout}" in r.description for r in report.results
            )

    def test_collection_cli_error_from_stdout_is_reported(self, runner):
        with inso_output(
            "Error: No data source found at path '/tmp/missing'\nTIP: use --workingDir",
            returncode=1,
        ):
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))

        assert report.failed_count == 1
        assert "No data source found" in report.raw_output
        assert "No data source found" not in report.results[0].description
        assert "TIP:" not in report.results[0].description

    def test_collection_nonzero_exit_with_tap_results_still_fails(self, runner):
        with inso_output("TAP version 13\n1..1\nok 1 - Passed\n", returncode=1):
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))

        assert report.passed_count == 1
        assert report.failed_count == 1
        assert "Inso CLI Error" in report.results[-1].description

    def test_collection_cli_error_preserves_both_streams_only_in_raw_output(
        self, runner
    ):
        with inso_output(
            "Error: No data source found at path '/tmp/missing'",
            "Warning: using default configuration",
            returncode=1,
        ):
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))

        assert report.failed_count == 1
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
            assert report.plan_end == report.total_tests == 1
            assert f"{options.execution_timeout}" in report.raw_output
            assert any(
                f"{options.execution_timeout}" in r.description for r in report.results
            )

    def test_test_cli_error_from_stdout_is_reported(self, runner):
        with inso_output("No test suites found; cannot run tests.", returncode=1):
            report = runner.run_test(InsoTestOptions(working_dir="/path"))

        assert report.failed_count == 1
        assert "No test suites found" in report.raw_output
        assert "No test suites found" not in report.results[0].description
