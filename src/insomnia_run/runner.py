import os
import signal
from pathlib import Path
import re
import tempfile

# Inso must be executed as a subprocess.
import subprocess  # nosec B404

from .models import (
    InsoCollectionOptions,
    InsoRunReport,
    InsoTestOptions,
    RunType,
    RunError,
)
from .native import parse_native_report, validate_capture_headers
from .parser import TapParser


class InsoRunner:
    @staticmethod
    def _run_command(cmd: list[str], timeout: int):
        if os.name != "posix":
            raise NotImplementedError(
                "InsoRunner requires POSIX process groups (Linux/macOS); Windows is unsupported."
            )
        # Arguments are passed without a shell.
        with subprocess.Popen(  # nosec B603
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
            shell=False,
            umask=0o077,
            env={**os.environ, "INSO_TELEMETRY_DISABLED": "1"},
        ) as process:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except BaseException as error:
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
                    drained_stdout, drained_stderr = process.communicate(timeout=1)
                    if isinstance(error, subprocess.TimeoutExpired):
                        error.output = drained_stdout.encode("utf-8")
                        error.stderr = drained_stderr.encode("utf-8")
                except (OSError, subprocess.TimeoutExpired):
                    pass
                raise
            return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)

    def _supports_native_report(self) -> bool:
        try:
            # Capability discovery never runs a collection or interprets script logs.
            result = subprocess.run(  # nosec B603 B607
                ["inso", "run", "collection", "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
                env={**os.environ, "INSO_TELEMETRY_DISABLED": "1"},
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and bool(
            re.search(r"^\s+--output(?:\s|$)", result.stdout, re.M)
        )

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
    def _text(value: str | bytes | None) -> str:
        return (
            value.decode("utf-8", errors="replace")
            if isinstance(value, bytes)
            else value or ""
        )

    @staticmethod
    def _native_report(path: Path, options: InsoCollectionOptions) -> InsoRunReport:
        try:
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError("Native report is too large.")
            return parse_native_report(
                path.read_text(encoding="utf-8"),
                capture_headers=options.capture_response_headers,
            )
        except (ValueError, OSError):
            return InsoRunReport(
                plan_end=0,
                complete=False,
                run_error=RunError(
                    kind="protocol", message="Inso wrote an invalid native report."
                ),
            )

    def _completed_report(
        self,
        result: subprocess.CompletedProcess[str],
        options,
        run_type: RunType,
        native_path: Path | None,
    ) -> InsoRunReport:
        if native_path is not None and native_path.exists():
            report = self._native_report(native_path, options)
        else:
            report = (
                InsoRunReport(plan_end=0)
                if options.verbose
                else TapParser().parse(
                    result.stdout, require_tap=run_type == RunType.TEST
                )
            )
            if native_path is not None:
                self._missing_native_report(report, options, result.returncode)
        if (
            result.returncode != 0
            and not report.run_error
            and (result.returncode != 1 or not report.failed_count)
        ):
            report.complete = False
            report.run_error = RunError(
                kind="execution",
                message=f"Inso CLI exited with code {result.returncode}.",
            )
        return report

    @staticmethod
    def _missing_native_report(
        report: InsoRunReport, options: InsoCollectionOptions, returncode: int
    ) -> None:
        report.complete = False
        # Inso 13.3.1's bail path exits zero before saveReport().
        if not (
            options.bail
            and not options.verbose
            and returncode == 0
            and report.failed_count
            and not report.run_error
        ):
            report.run_error = RunError(
                kind="protocol", message="Inso did not write its native report."
            )

    def _execute(
        self,
        cmd: list[str],
        options,
        run_type: RunType,
        native_path: Path | None = None,
    ) -> InsoRunReport:
        try:
            result = self._run_command(cmd, options.execution_timeout)
        except subprocess.TimeoutExpired as error:
            stdout, stderr = self._text(error.output), self._text(error.stderr)
            if native_path is not None and native_path.exists():
                report = self._native_report(native_path, options)
            elif options.verbose:
                report = InsoRunReport(plan_end=0)
            else:
                report = TapParser().parse(stdout, require_tap=True)
            report.complete = False
            report.run_error = RunError(
                kind="timeout",
                message=(
                    f"Inso CLI timed out after {options.execution_timeout} seconds."
                    + (f" {report.run_error.message}" if report.run_error else "")
                ),
            )
        else:
            stdout, stderr = result.stdout, result.stderr
            report = self._completed_report(result, options, run_type, native_path)
        report.raw_output = stdout + stderr
        report.run_type = run_type
        report.target_name = options.identifier
        return report

    def run_collection(self, options: InsoCollectionOptions) -> InsoRunReport:
        headers = validate_capture_headers(options.capture_response_headers)
        cmd = self._base_cmd(RunType.COLLECTION, options.working_dir)
        self._apply_common_options(cmd, options)
        self._apply_collection_options(cmd, options)
        native = self._supports_native_report()
        if not native and (options.verbose or headers):
            raise ValueError(
                "Native collection reporting is required for verbose or response header capture."
            )
        with tempfile.TemporaryDirectory(prefix="insomnia-run-private-") as directory:
            path = Path(directory) / "native.json" if native else None
            if path is not None:
                cmd.extend(["--output", str(path)])
                if headers:
                    cmd.extend(["--includeFullData", "redact", "--acceptRisk"])
            if options.identifier:
                cmd.extend(["--", options.identifier])
            return self._execute(cmd, options, RunType.COLLECTION, path)

    def run_test(self, options: InsoTestOptions) -> InsoRunReport:
        if options.verbose:
            raise ValueError("verbose is unsafe for legacy test TAP reporting.")
        cmd = self._base_cmd(RunType.TEST, options.working_dir)
        self._apply_common_options(cmd, options)
        self._apply_test_options(cmd, options)
        if options.identifier:
            cmd.extend(["--", options.identifier])

        return self._execute(cmd, options, RunType.TEST)
