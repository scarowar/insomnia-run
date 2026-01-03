import pytest
from insomnia_run.models import (
    RunType,
    InsoStatus,
    InsoResult,
    InsoRunReport,
    InsoCollectionOptions,
    InsoTestOptions,
)


class TestRunTypeEnum:
    def test_collection_value(self):
        assert RunType.COLLECTION.value == "collection"

    def test_test_value(self):
        assert RunType.TEST.value == "test"

    def test_is_string_enum(self):
        assert isinstance(RunType.COLLECTION, str)
        assert RunType.COLLECTION == "collection"


class TestInsoStatusEnum:
    def test_pass_value(self):
        assert InsoStatus.PASS.value == "PASS"

    def test_fail_value(self):
        assert InsoStatus.FAIL.value == "FAIL"

    def test_skip_value(self):
        assert InsoStatus.SKIP.value == "SKIP"


class TestInsoResult:
    def test_create_passing_result(self):
        result = InsoResult(id=1, status=InsoStatus.PASS, description="Test passed")
        assert result.id == 1
        assert result.status == InsoStatus.PASS
        assert result.description == "Test passed"

    def test_create_failing_result(self):
        result = InsoResult(id=2, status=InsoStatus.FAIL, description="Test failed")
        assert result.status == InsoStatus.FAIL


class TestInsoRunReport:
    def test_empty_report(self):
        report = InsoRunReport(plan_end=0)
        assert report.total_tests == 0
        assert report.passed_count == 0
        assert report.failed_count == 0
        assert report.skipped_count == 0
        assert report.success_rate == 0.0

    def test_all_passing_report(self):
        report = InsoRunReport(
            plan_end=3,
            results=[
                InsoResult(id=1, status=InsoStatus.PASS, description="Test 1"),
                InsoResult(id=2, status=InsoStatus.PASS, description="Test 2"),
                InsoResult(id=3, status=InsoStatus.PASS, description="Test 3"),
            ],
        )
        assert report.total_tests == 3
        assert report.passed_count == 3
        assert report.failed_count == 0
        assert report.success_rate == 100.0

    def test_mixed_results_report(self):
        report = InsoRunReport(
            plan_end=4,
            results=[
                InsoResult(id=1, status=InsoStatus.PASS, description="Pass 1"),
                InsoResult(id=2, status=InsoStatus.FAIL, description="Fail 1"),
                InsoResult(id=3, status=InsoStatus.PASS, description="Pass 2"),
                InsoResult(id=4, status=InsoStatus.SKIP, description="Skip 1"),
            ],
        )
        assert report.total_tests == 4
        assert report.passed_count == 2
        assert report.failed_count == 1
        assert report.skipped_count == 1
        assert report.success_rate == 50.0

    def test_default_run_type(self):
        report = InsoRunReport(plan_end=0)
        assert report.run_type == RunType.COLLECTION

    def test_custom_run_type(self):
        report = InsoRunReport(plan_end=0, run_type=RunType.TEST)
        assert report.run_type == RunType.TEST

    def test_default_tap_version(self):
        report = InsoRunReport(plan_end=0)
        assert report.tap_version == 13


class TestInsoCollectionOptions:
    def test_minimal_options(self):
        options = InsoCollectionOptions(working_dir="/path/to/insomnia")
        assert options.working_dir == "/path/to/insomnia"
        assert options.identifier is None
        assert options.environment is None
        assert options.bail is False

    def test_full_options(self):
        options = InsoCollectionOptions(
            working_dir="/path/to/insomnia",
            identifier="My Collection",
            environment="Production",
            request_name_pattern=".*",
            item=["req_001", "req_002"],
            globals="globals.json",
            delay_request=100,
            request_timeout=30000,
            env_var={"API_KEY": "secret"},
            iteration_count=5,
            iteration_data="data.csv",
            bail=True,
            disable_cert_validation=True,
            https_proxy="https://proxy:8080",
            http_proxy="https://proxy:8080",
            no_proxy="localhost,127.0.0.1",
            data_folders=["./data", "/home/user/data"],
            verbose=True,
        )
        assert options.identifier == "My Collection"
        assert options.bail is True
        assert options.env_var["API_KEY"] == "secret"
        assert len(options.item) == 2


class TestInsoTestOptions:
    def test_minimal_options(self):
        options = InsoTestOptions(working_dir="/path/to/insomnia")
        assert options.working_dir == "/path/to/insomnia"
        assert options.keep_file is False

    def test_full_options(self):
        options = InsoTestOptions(
            working_dir="/path/to/insomnia",
            identifier="My Test Suite",
            environment="Staging",
            test_name_pattern=".*login.*",
            bail=True,
            keep_file=True,
            request_timeout=60000,
            disable_cert_validation=True,
            https_proxy="https://proxy:8080",
            http_proxy="https://proxy:8080",
            no_proxy="localhost",
            data_folders=["/data"],
            verbose=True,
        )
        assert options.test_name_pattern == ".*login.*"
        assert options.keep_file is True
