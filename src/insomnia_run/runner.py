import subprocess

from .models import (
    InsoCollectionOptions,
    InsoResult,
    InsoRunReport,
    InsoStatus,
    InsoTestOptions,
    RunType,
)
from .parser import TapParser


class InsoRunner:
    @staticmethod
    def _base_cmd(run_type: RunType, working_dir: str, identifier: str | None):
        cmd = ["inso", "run", run_type.value]

        if identifier:
            cmd.append(identifier)

        cmd.extend(["-w", working_dir, "--reporter", "tap", "--ci"])
        return cmd

    @staticmethod
    def _apply_common_options(cmd: list[str], options):
        if options.environment:
            cmd.extend(["--env", options.environment])

        if options.request_timeout:
            cmd.extend(["--requestTimeout", str(options.request_timeout)])

        if options.disable_cert_validation:
            cmd.append("--disableCertValidation")

        if options.https_proxy:
            cmd.extend(["--httpsProxy", options.https_proxy])

        if options.http_proxy:
            cmd.extend(["--httpProxy", options.http_proxy])

        if options.no_proxy:
            cmd.extend(["--noProxy", options.no_proxy])

        if options.data_folders:
            for folder in options.data_folders:
                cmd.extend(["--dataFolders", folder])

        if options.verbose:
            cmd.append("--verbose")

    @staticmethod
    def _apply_collection_options(cmd: list[str], options: InsoCollectionOptions):
        if options.request_name_pattern:
            cmd.extend(["--requestNamePattern", options.request_name_pattern])

        if options.item:
            for item_id in options.item:
                cmd.extend(["--item", item_id])

        if options.globals:
            cmd.extend(["--globals", options.globals])

        if options.delay_request:
            cmd.extend(["--delay-request", str(options.delay_request)])

        if options.env_var:
            for key, value in options.env_var.items():
                cmd.extend(["--env-var", f"{key}={value}"])

        if options.iteration_count:
            cmd.extend(["--iteration-count", str(options.iteration_count)])

        if options.iteration_data:
            cmd.extend(["--iteration-data", options.iteration_data])

        if options.bail:
            cmd.append("--bail")

    @staticmethod
    def _apply_test_options(cmd: list[str], options: InsoTestOptions):
        if options.test_name_pattern:
            cmd.extend(["--testNamePattern", options.test_name_pattern])

        if options.bail:
            cmd.append("--bail")

        if options.keep_file:
            cmd.append("--keepFile")

    @staticmethod
    def _add_error_result_if_needed(report: InsoRunReport, result) -> None:
        """Add a synthetic error result if inso CLI failed with no TAP output."""
        if result.returncode != 0 and report.total_tests == 0:
            error_msg = result.stderr.strip() or "Unknown error"
            report.results.append(
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description=f"Inso CLI Error: {error_msg}",
                )
            )

    def run_collection(self, options: InsoCollectionOptions) -> InsoRunReport:
        cmd = self._base_cmd(
            RunType.COLLECTION, options.working_dir, options.identifier
        )
        self._apply_common_options(cmd, options)
        self._apply_collection_options(cmd, options)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            report = InsoRunReport(plan_end=0, run_type=RunType.COLLECTION)
            report.target_name = options.identifier
            report.raw_output = "Inso CLI timed out after 5 minutes"
            report.results.append(
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="Inso CLI Error: Command timed out after 5 minutes",
                )
            )
            return report

        full_output = result.stdout + result.stderr

        parser = TapParser()
        report = parser.parse(result.stdout)
        report.raw_output = full_output
        report.run_type = RunType.COLLECTION
        report.target_name = options.identifier

        self._add_error_result_if_needed(report, result)

        return report

    def run_test(self, options: InsoTestOptions) -> InsoRunReport:
        cmd = self._base_cmd(RunType.TEST, options.working_dir, options.identifier)
        self._apply_common_options(cmd, options)
        self._apply_test_options(cmd, options)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            report = InsoRunReport(plan_end=0, run_type=RunType.TEST)
            report.target_name = options.identifier
            report.raw_output = "Inso CLI timed out after 5 minutes"
            report.results.append(
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="Inso CLI Error: Command timed out after 5 minutes",
                )
            )
            return report

        full_output = result.stdout + result.stderr

        parser = TapParser()
        report = parser.parse(result.stdout)
        report.raw_output = full_output
        report.run_type = RunType.TEST
        report.target_name = options.identifier

        self._add_error_result_if_needed(report, result)

        return report
