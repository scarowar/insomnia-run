import contextlib
from unittest.mock import MagicMock, patch

import pytest

from insomnia_run.models import (
    InsoCollectionOptions,
    InsoStatus,
    InsoTestOptions,
    RunType,
)
from insomnia_run.runner import InsoRunner


class TestInsoRunnerCollection:
    @pytest.fixture
    def runner(self):
        return InsoRunner()

    @pytest.fixture
    def mock_subprocess(self):
        with patch("insomnia_run.runner.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = """TAP version 13
1..1
ok 1 - Test passed
"""
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            yield mock_run

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
        assert cmd[3] == "My Collection"

    def test_collection_with_environment(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path", environment="Production")
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--env" in cmd
        env_idx = cmd.index("--env")
        assert cmd[env_idx + 1] == "Production"

    def test_collection_with_request_pattern(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path", request_name_pattern=".*login.*")
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--requestNamePattern" in cmd
        idx = cmd.index("--requestNamePattern")
        assert cmd[idx + 1] == ".*login.*"

    def test_collection_with_multiple_items(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path", item=["req_001", "req_002", "req_003"])
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
        options = InsoCollectionOptions(working_dir="/path", disable_cert_validation=True)
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
        _, kwargs = mock_subprocess.call_args
        assert kwargs["timeout"] == 123

    def test_collection_timeout_error_message(self, runner):
        from subprocess import TimeoutExpired

        with patch(
            "insomnia_run.runner.subprocess.run",
            side_effect=TimeoutExpired(cmd="inso", timeout=77),
        ):
            options = InsoCollectionOptions(working_dir="/path", execution_timeout=77)
            report = runner.run_collection(options)
            assert f"{options.execution_timeout}" in report.raw_output
            assert any(f"{options.execution_timeout}" in r.description for r in report.results)


class TestInsoRunnerTest:
    @pytest.fixture
    def runner(self):
        return InsoRunner()

    @pytest.fixture
    def mock_subprocess(self):
        with patch("insomnia_run.runner.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = """ok 1 Test Suite Test Name
# tests 1
# pass 1
1..1
"""
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            yield mock_run

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
        _, kwargs = mock_subprocess.call_args
        assert kwargs["timeout"] == 456

    def test_test_timeout_error_message(self, runner):
        from subprocess import TimeoutExpired

        with patch(
            "insomnia_run.runner.subprocess.run",
            side_effect=TimeoutExpired(cmd="inso", timeout=88),
        ):
            options = InsoTestOptions(working_dir="/path", execution_timeout=88)
            report = runner.run_test(options)
            assert f"{options.execution_timeout}" in report.raw_output
            assert any(f"{options.execution_timeout}" in r.description for r in report.results)


class TestRunnerCapturePolicies:
    """Ticket 11: redaction at capture, timeout capture, false-pass guard, error preservation."""

    @pytest.fixture
    def runner(self):
        return InsoRunner()

    @contextlib.contextmanager
    def _mock(self, stdout, stderr="", returncode=0):
        with patch("insomnia_run.runner.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = stdout
            mock_result.stderr = stderr
            mock_result.returncode = returncode
            mock_run.return_value = mock_result
            yield mock_run

    def test_env_var_values_redacted_from_raw_output(self, runner):
        options = InsoCollectionOptions(
            working_dir="/path", env_var={"API_KEY": "supersecretvalue123"}
        )
        stdout = "TAP version 13\n1..1\nok 1 - done\nrequest header: API_KEY=supersecretvalue123\n"
        with self._mock(stdout) as _:
            report = runner.run_collection(options)
        assert "supersecretvalue123" not in report.raw_output
        assert "***REDACTED***" in report.raw_output

    def test_authorization_header_redacted(self, runner):
        options = InsoCollectionOptions(working_dir="/path")
        stdout = "TAP version 13\n1..1\nok 1 - done\nAuthorization: Bearer abcdef123456\n"
        with self._mock(stdout) as _:
            report = runner.run_collection(options)
        assert "abcdef123456" not in report.raw_output
        assert "Authorization:" in report.raw_output
        assert "***REDACTED***" in report.raw_output

    def test_tokenized_url_redacted(self, runner):
        options = InsoCollectionOptions(working_dir="/path")
        stdout = "TAP version 13\n1..1\nok 1 - done\nGET https://api.example.com/data?token=abcdef123456&x=1\n"
        with self._mock(stdout) as _:
            report = runner.run_collection(options)
        assert "abcdef123456" not in report.raw_output
        assert "token=***REDACTED***" in report.raw_output

    def test_short_env_values_not_redacted(self, runner):
        options = InsoCollectionOptions(working_dir="/path", env_var={"X": "ab"})
        stdout = "TAP version 13\n1..1\nok 1 - value ab intact\n"
        with self._mock(stdout) as _:
            report = runner.run_collection(options)
        assert "ab intact" in report.raw_output

    def test_timeout_captures_partial_output(self, runner):
        from subprocess import TimeoutExpired

        with patch(
            "insomnia_run.runner.subprocess.run",
            side_effect=TimeoutExpired(
                cmd="inso", timeout=77, output=b"TAP version 13\n1..2\nok 1 - partial\n"
            ),
        ):
            options = InsoCollectionOptions(working_dir="/path", execution_timeout=77)
            report = runner.run_collection(options)
        assert "ok 1 - partial" in report.raw_output
        assert "77" in report.raw_output

    def test_zero_results_with_zero_exit_is_failure_not_pass(self, runner):
        with self._mock("") as _:
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))
        assert report.total_tests == 1
        assert report.results[0].status == InsoStatus.FAIL
        assert report.diagnostics

    def test_nonzero_exit_with_partial_results_records_diagnostic(self, runner):
        stdout = "TAP version 13\n1..2\nok 1 - first\nnot ok 2 - second\n"
        with self._mock(stdout, stderr="inso crashed mid-run", returncode=1) as _:
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))
        assert report.total_tests == 2
        assert report.failed_count == 1
        assert any("inso crashed mid-run" in d for d in report.diagnostics)

    def test_nonzero_exit_without_results_synthesizes_failure(self, runner):
        with self._mock("", stderr="boom: no collection found", returncode=1) as _:
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))
        assert report.results[0].status == InsoStatus.FAIL
        assert "boom: no collection found" in report.results[0].description

    def test_synthetic_error_result_is_capped(self, runner):
        with self._mock("", stderr="x" * 10_000, returncode=1) as _:
            report = runner.run_collection(InsoCollectionOptions(working_dir="/path"))
        assert len(report.results[0].description) <= 4100

    def test_redaction_applies_to_test_runs(self, runner):
        options = InsoTestOptions(working_dir="/path")
        stdout = "ok 1 suite\n# tests 1\n# pass 1\n1..1\nAuthorization: Bearer abcdef123456\n"
        with self._mock(stdout) as _:
            report = runner.run_test(options)
        assert "abcdef123456" not in report.raw_output

    def test_redaction_covers_parsed_messages_not_just_raw_output(self, runner):
        options = InsoCollectionOptions(
            working_dir="/path", env_var={"API_KEY": "supersecretvalue123"}
        )
        stdout = (
            "TAP version 13\n1..1\nnot ok 1 - call failed\n"
            "error: expected 200 | ACTUAL: supersecretvalue123 | EXPECTED: 200\n"
        )
        with self._mock(stdout) as _:
            report = runner.run_collection(options)
        assert "supersecretvalue123" not in report.raw_output
        assert report.results[0].message is not None
        assert "supersecretvalue123" not in report.results[0].message


class TestRedactionCoverage:

    @pytest.fixture
    def runner(self):
        return InsoRunner()

    @contextlib.contextmanager
    def _mock(self, stdout, stderr="", returncode=0):
        with patch("insomnia_run.runner.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = stdout
            mock_result.stderr = stderr
            mock_result.returncode = returncode
            mock_run.return_value = mock_result
            yield mock_run

    @pytest.mark.parametrize(
        "leak",
        [
            "Authorization: Bearer secrettoken12345",
            "  Authorization: Bearer indented_secret12345",
            '{"Authorization": "Bearer json_secret123456"}',
            "x-forwarded-authorization: Bearer lower_secret123456",
        ],
    )
    def test_authorization_forms_redacted_anywhere_in_line(self, runner, leak):
        with self._mock(f"TAP version 13\n1..1\nok 1 - x\n{leak}\n") as _:
            report = runner.run_collection(InsoCollectionOptions(working_dir="/p"))
        token = leak.split()[-1]
        assert token not in report.raw_output
        assert "***REDACTED***" in report.raw_output

    def test_api_key_and_cookie_headers_redacted(self, runner):
        with self._mock(
            "TAP version 13\n1..1\nok 1 - x\nX-Api-Key: abcdef123456\nCookie: session=qwerty1234567\n"
        ) as _:
            report = runner.run_collection(InsoCollectionOptions(working_dir="/p"))
        assert "abcdef123456" not in report.raw_output
        assert "qwerty1234567" not in report.raw_output

    @pytest.mark.parametrize(
        "url",
        [
            "https://api.example.com/x?key=secretkey123456",
            "https://api.example.com/x?client_secret=topsecret123456",
            "https://api.example.com/x?signature=calculated12345678",
        ],
    )
    def test_extended_tokenized_urls_redacted(self, runner, url):
        with self._mock(f"TAP version 13\n1..1\nok 1 - x\nGET {url}\n") as _:
            report = runner.run_collection(InsoCollectionOptions(working_dir="/p"))
        assert url not in report.raw_output

    def test_missing_inso_binary_is_a_clean_failure(self, runner):
        with patch(
            "insomnia_run.runner.subprocess.run",
            side_effect=FileNotFoundError(2, "No such file or directory", "inso"),
        ):
            report = runner.run_collection(InsoCollectionOptions(working_dir="/p"))
        assert report.total_tests == 1
        assert report.results[0].status == InsoStatus.FAIL
        assert "Could not execute Inso CLI" in report.results[0].description
        assert report.diagnostics

    def test_synthetic_error_includes_exit_code(self, runner):
        with self._mock("", stderr="boom", returncode=3) as _:
            report = runner.run_collection(InsoCollectionOptions(working_dir="/p"))
        assert "exit code 3" in report.results[0].description


class TestAddMask:
    def test_add_mask_emitted_for_env_var_secrets(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        from unittest.mock import MagicMock, patch

        from insomnia_run.models import InsoCollectionOptions
        from insomnia_run.runner import InsoRunner

        with patch("insomnia_run.runner.subprocess.run") as mock_run:
            m = MagicMock()
            m.stdout = "TAP version 13\n1..1\nok 1 - x\n"
            m.stderr = ""
            m.returncode = 0
            mock_run.return_value = m
            runner = InsoRunner()
            report = runner.run_collection(
                InsoCollectionOptions(working_dir="/tmp", env_var={"K": "supersecret12345"})
            )
            assert report.total_tests == 1
        err = capsys.readouterr().err
        assert "::add-mask::supersecret12345" in err

    def test_add_mask_escapes_percent(self, monkeypatch, capsys):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        from unittest.mock import MagicMock, patch

        from insomnia_run.models import InsoCollectionOptions
        from insomnia_run.runner import InsoRunner

        with patch("insomnia_run.runner.subprocess.run") as mock_run:
            m = MagicMock()
            m.stdout = "TAP version 13\n1..1\nok 1 - x\n"
            m.stderr = ""
            m.returncode = 0
            mock_run.return_value = m
            runner = InsoRunner()
            runner.run_collection(
                InsoCollectionOptions(working_dir="/tmp", env_var={"K": "a%b\nc\rd"})
            )
        err = capsys.readouterr().err
        # runner masks only values >=4 chars, so a%b\nc\rd (6 chars) should be masked with escaping
        assert "::add-mask::" in err
        assert "%25" in err or "a%b" not in err  # escaped percent
