import pytest
from unittest.mock import patch, MagicMock
from insomnia_run.runner import InsoRunner
from insomnia_run.models import InsoCollectionOptions, InsoTestOptions, RunType


class TestInsoRunnerCollection:
    @pytest.fixture
    def runner(self):
        return InsoRunner()

    @pytest.fixture
    def mock_subprocess(self):
        with patch('insomnia_run.runner.subprocess.run') as mock_run:
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
        options = InsoCollectionOptions(
            working_dir="/path",
            identifier="My Collection"
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "My Collection" in cmd
        assert cmd[3] == "My Collection"

    def test_collection_with_environment(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            environment="Production"
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--env" in cmd
        env_idx = cmd.index("--env")
        assert cmd[env_idx + 1] == "Production"

    def test_collection_with_request_pattern(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            request_name_pattern=".*login.*"
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--requestNamePattern" in cmd
        idx = cmd.index("--requestNamePattern")
        assert cmd[idx + 1] == ".*login.*"

    def test_collection_with_multiple_items(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            item=["req_001", "req_002", "req_003"]
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        item_count = cmd.count("--item")
        assert item_count == 3

    def test_collection_with_env_vars(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            env_var={"API_KEY": "secret", "TOKEN": "abc123"}
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--env-var" in cmd
        assert "API_KEY=secret" in cmd
        assert "TOKEN=abc123" in cmd

    def test_collection_with_timeouts(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            delay_request=500,
            request_timeout=30000
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--delay-request" in cmd
        assert "500" in cmd
        assert "--requestTimeout" in cmd
        assert "30000" in cmd

    def test_collection_with_iteration_options(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            iteration_count=5,
            iteration_data="/data/test.csv"
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--iteration-count" in cmd
        assert "5" in cmd
        assert "--iteration-data" in cmd
        assert "/data/test.csv" in cmd

    def test_collection_with_bail(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            bail=True
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--bail" in cmd

    def test_collection_with_ssl_disabled(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            disable_cert_validation=True
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--disableCertValidation" in cmd

    def test_collection_with_proxies(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            https_proxy="https://proxy:8080",
            http_proxy="https://proxy:8080",
            no_proxy="localhost,127.0.0.1"
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
            working_dir="/path",
            data_folders=["./data", "/home/user/data"]
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        folder_count = cmd.count("--dataFolders")
        assert folder_count == 2

    def test_collection_with_verbose(self, runner, mock_subprocess):
        options = InsoCollectionOptions(
            working_dir="/path",
            verbose=True
        )
        runner.run_collection(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--verbose" in cmd

    def test_collection_report_type(self, runner, mock_subprocess):
        options = InsoCollectionOptions(working_dir="/path")
        report = runner.run_collection(options)

        assert report.run_type == RunType.COLLECTION


class TestInsoRunnerTest:
    @pytest.fixture
    def runner(self):
        return InsoRunner()

    @pytest.fixture
    def mock_subprocess(self):
        with patch('insomnia_run.runner.subprocess.run') as mock_run:
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
        options = InsoTestOptions(
            working_dir="/path",
            identifier="My Test Suite"
        )
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "My Test Suite" in cmd

    def test_test_with_name_pattern(self, runner, mock_subprocess):
        options = InsoTestOptions(
            working_dir="/path",
            test_name_pattern=".*auth.*"
        )
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--testNamePattern" in cmd
        idx = cmd.index("--testNamePattern")
        assert cmd[idx + 1] == ".*auth.*"

    def test_test_with_bail(self, runner, mock_subprocess):
        options = InsoTestOptions(
            working_dir="/path",
            bail=True
        )
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--bail" in cmd

    def test_test_with_keep_file(self, runner, mock_subprocess):
        options = InsoTestOptions(
            working_dir="/path",
            keep_file=True
        )
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--keepFile" in cmd

    def test_test_with_timeout(self, runner, mock_subprocess):
        options = InsoTestOptions(
            working_dir="/path",
            request_timeout=60000
        )
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--requestTimeout" in cmd
        assert "60000" in cmd

    def test_test_with_ssl_disabled(self, runner, mock_subprocess):
        options = InsoTestOptions(
            working_dir="/path",
            disable_cert_validation=True
        )
        runner.run_test(options)

        cmd = mock_subprocess.call_args[0][0]
        assert "--disableCertValidation" in cmd

    def test_test_with_proxies(self, runner, mock_subprocess):
        options = InsoTestOptions(
            working_dir="/path",
            https_proxy="https://proxy:8080",
            http_proxy="https://proxy:8080",
            no_proxy="localhost"
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
        options = InsoTestOptions(
            working_dir="/path",
            identifier="Auth Tests"
        )
        report = runner.run_test(options)

        assert report.target_name == "Auth Tests"
