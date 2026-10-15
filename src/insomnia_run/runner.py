import os
import signal
import subprocess  # nosec B404 - Inso must be executed as a subprocess.

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
    def _run_command(cmd: list[str], timeout: int):
        if os.name != "posix":
            raise NotImplementedError(
                "InsoRunner requires POSIX process groups (Linux/macOS); Windows is unsupported."
            )
        with subprocess.Popen(  # nosec B603 - arguments are passed without a shell.
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
            shell=False,
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except BaseException:
                # A new session does not inherit terminal interrupts; stop it too.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except OSError:
                    try:
                        process.kill()
                    except OSError:
                        pass
                try:
                    process.communicate(timeout=1)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                raise
            return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)

    @staticmethod
    def _base_cmd(run_type: RunType, working_dir: str):
        return [
            "inso",
            "run",
            run_type.value,
            "-w",
            working_dir,
            "--reporter",
            "tap",
            "--ci",
        ]

    @staticmethod
    def _apply_common_options(
        cmd: list[str], options: InsoCollectionOptions | InsoTestOptions
    ):
        if options.environment:
            cmd.extend(["--env", options.environment])

        if options.request_timeout is not None:
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

        if options.delay_request is not None:
            cmd.extend(["--delay-request", str(options.delay_request)])

        if options.env_var:
            if isinstance(options.env_var, dict):
                env_vars = [f"{key}={value}" for key, value in options.env_var.items()]
            else:
                env_vars = options.env_var
            for value in env_vars:
                cmd.extend(["--env-var", value])

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
        """Preserve a nonzero exit without publishing arbitrary diagnostics."""
        if result.returncode == 0 or report.failed_count > 0:
            return

        next_id = max((item.id for item in report.results), default=0) + 1
        report.results.append(
            InsoResult(
                id=next_id,
                status=InsoStatus.FAIL,
                description=f"Inso CLI Error: Process exited with code {result.returncode}.",
            )
        )
        report.plan_end = max(report.plan_end, next_id)

    def run_collection(self, options: InsoCollectionOptions) -> InsoRunReport:
        cmd = self._base_cmd(RunType.COLLECTION, options.working_dir)
        self._apply_common_options(cmd, options)
        self._apply_collection_options(cmd, options)
        if options.identifier:
            cmd.extend(["--", options.identifier])

        try:
            result = self._run_command(cmd, options.execution_timeout)
        except subprocess.TimeoutExpired:
            report = InsoRunReport(plan_end=1, run_type=RunType.COLLECTION)
            report.target_name = options.identifier
            report.raw_output = (
                f"Inso CLI timed out after {options.execution_timeout} seconds"
            )
            report.results.append(
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description=f"Inso CLI Error: Command timed out after {options.execution_timeout} seconds",
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
        cmd = self._base_cmd(RunType.TEST, options.working_dir)
        self._apply_common_options(cmd, options)
        self._apply_test_options(cmd, options)
        if options.identifier:
            cmd.extend(["--", options.identifier])

        try:
            result = self._run_command(cmd, options.execution_timeout)
        except subprocess.TimeoutExpired:
            report = InsoRunReport(plan_end=1, run_type=RunType.TEST)
            report.target_name = options.identifier
            report.raw_output = (
                f"Inso CLI timed out after {options.execution_timeout} seconds"
            )
            report.results.append(
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description=f"Inso CLI Error: Command timed out after {options.execution_timeout} seconds",
                )
            )
            return report

        full_output = result.stdout + result.stderr

        parser = TapParser()
        report = parser.parse(result.stdout, require_tap=True)
        report.raw_output = full_output
        report.run_type = RunType.TEST
        report.target_name = options.identifier

        self._add_error_result_if_needed(report, result)

        return report
