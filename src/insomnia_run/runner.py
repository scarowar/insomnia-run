import os
import signal
from collections.abc import Mapping
from pathlib import Path
import re
import tempfile
import time
from threading import Event, Thread
from typing import IO
from urllib.parse import urlencode

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
from .privacy import Redactor

_MAX_CAPTURE_BYTES = 32 * 1024 * 1024
_RUNTIME_ENVIRONMENT = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "TMP",
        "TEMP",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "LC_COLLATE",
        "LC_MESSAGES",
        "LC_MONETARY",
        "LC_NUMERIC",
        "LC_TIME",
        "TZ",
        "CI",
        "TERM",
        "NO_COLOR",
        "FORCE_COLOR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
        "NODE_USE_SYSTEM_CA",
    }
)
_PUBLIC_GITHUB_CONTEXT = {
    "GITHUB_ACTIONS",
    "GITHUB_ACTION",
    "GITHUB_ACTION_PATH",
    "GITHUB_ACTION_REF",
    "GITHUB_ACTION_REPOSITORY",
    "GITHUB_ACTOR",
    "GITHUB_ACTOR_ID",
    "GITHUB_API_URL",
    "GITHUB_BASE_REF",
    "GITHUB_EVENT_NAME",
    "GITHUB_GRAPHQL_URL",
    "GITHUB_HEAD_REF",
    "GITHUB_JOB",
    "GITHUB_REF",
    "GITHUB_REF_NAME",
    "GITHUB_REF_TYPE",
    "GITHUB_REPOSITORY",
    "GITHUB_REPOSITORY_ID",
    "GITHUB_REPOSITORY_OWNER",
    "GITHUB_REPOSITORY_OWNER_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_NUMBER",
    "GITHUB_SERVER_URL",
    "GITHUB_SHA",
    "GITHUB_WORKFLOW",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_WORKFLOW_SHA",
    "GITHUB_WORKSPACE",
}


def _inso_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """Pass supported runtime settings only; unknown variables are never inherited."""
    return {
        **{
            key: environ[key]
            for key in _RUNTIME_ENVIRONMENT | _PUBLIC_GITHUB_CONTEXT
            if key in environ
        },
        "INSO_TELEMETRY_DISABLED": "1",
    }


class _OutputLimitError(subprocess.SubprocessError):
    def __init__(self):
        super().__init__(
            f"Inso CLI output exceeded the capture limit ({_MAX_CAPTURE_BYTES} bytes). Reduce collection logging."
        )


def _terminate_process(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        try:
            process.kill()
        except OSError:
            pass


def _capture_size(streams: tuple[IO[bytes], IO[bytes]]) -> int:
    return sum(os.fstat(stream.fileno()).st_size for stream in streams)


def _read_captures(streams: tuple[IO[bytes], IO[bytes]]) -> tuple[str, str]:
    if _capture_size(streams) > _MAX_CAPTURE_BYTES:
        raise _OutputLimitError()
    stdout, stderr = streams
    stdout.seek(0)
    stderr.seek(0)
    return (
        stdout.read(_MAX_CAPTURE_BYTES).decode("utf-8", errors="replace"),
        stderr.read(_MAX_CAPTURE_BYTES).decode("utf-8", errors="replace"),
    )


def _watch_output(
    process: subprocess.Popen[str],
    streams: tuple[IO[bytes], IO[bytes]],
    stopped: Event,
    exceeded: Event,
) -> None:
    while not stopped.wait(0.01):
        if _capture_size(streams) > _MAX_CAPTURE_BYTES:
            exceeded.set()
            _terminate_process(process)
            return


def _wait_for_inso(
    process: subprocess.Popen[str], streams: tuple[IO[bytes], IO[bytes]], timeout: int
) -> tuple[str, str]:
    stopped, exceeded = Event(), Event()
    watcher = Thread(
        target=_watch_output,
        args=(process, streams, stopped, exceeded),
        name="insomnia-output-limit",
        daemon=True,
    )
    watcher.start()
    try:
        process.communicate(timeout=timeout)
    except BaseException as error:
        _terminate_process(process)
        try:
            process.communicate(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if isinstance(error, subprocess.TimeoutExpired):
            stdout, stderr = _read_captures(streams)
            error.output, error.stderr = stdout.encode("utf-8"), stderr.encode("utf-8")
        raise
    else:
        # Descendants must not keep writing to capture files after the parent exits.
        _terminate_process(process)
    finally:
        stopped.set()
        watcher.join()
    if exceeded.is_set():
        raise _OutputLimitError()
    return _read_captures(streams)


class InsoConfigurationError(ValueError):
    """A fixed, public-safe diagnostic that must never contain input values."""


class InsoRunner:
    def __init__(
        self, *, verified_version: str | None = None, redactor: Redactor | None = None
    ):
        self._verified_version = verified_version
        self._redactor = redactor or Redactor()

    @staticmethod
    def _run_command(cmd: list[str], timeout: int):
        if os.name != "posix":
            raise NotImplementedError(
                "InsoRunner requires POSIX process groups (Linux/macOS); Windows is unsupported."
            )
        # Arguments are passed without a shell.
        with (
            tempfile.TemporaryFile() as stdout_capture,
            tempfile.TemporaryFile() as stderr_capture,
            subprocess.Popen(  # nosec B603
                cmd,
                stdout=stdout_capture,
                stderr=stderr_capture,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
                shell=False,
                umask=0o077,
                env=_inso_environment(os.environ),
            ) as process,
        ):
            stdout, stderr = _wait_for_inso(
                process, (stdout_capture, stderr_capture), timeout
            )
            return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr)

    def _supports_native_report(self) -> bool:
        if self._verified_version in {"12.2.0", "12.6.0", "13.1.0", "13.3.1"}:
            return True
        try:
            # Capability discovery never runs a collection or interprets script logs.
            result = self._run_command(["inso", "run", "collection", "--help"], 15)
        except _OutputLimitError as error:
            raise InsoConfigurationError(
                "Inso capability discovery exceeded its output capture limit."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise InsoConfigurationError(
                "Inso capability discovery timed out. Check that "
                "'inso run collection --help' completes, then retry."
            ) from error
        if result.returncode != 0:
            raise InsoConfigurationError(
                "Inso capability discovery failed. Check that "
                "'inso run collection --help' succeeds, then retry."
            )
        return bool(re.search(r"^\s+(?:-\w,\s+)?--output\b", result.stdout, re.M))

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
                env_vars = [
                    urlencode({key: value}) for key, value in options.env_var.items()
                ]
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
                message=self._execution_error_message(result, options),
            )
        return report

    def _execution_error_message(
        self, result: subprocess.CompletedProcess[str], options
    ) -> str:
        redactor = Redactor(
            self._redactor.values, env_vars=getattr(options, "env_var", None)
        )
        lines = [
            line.strip()
            for line in redactor.redact(result.stderr).splitlines()
            if line.strip()
        ]
        diagnostic = (
            "\n".join(lines[-6:])
            .encode("utf-8")[-2048:]
            .decode("utf-8", errors="ignore")
        )
        message = f"Inso CLI exited with code {result.returncode}."
        return message + ("\n" + diagnostic if diagnostic else "")

    @staticmethod
    def _missing_native_report(
        report: InsoRunReport, options: InsoCollectionOptions, returncode: int
    ) -> None:
        report.complete = False
        if report.run_error:
            return
        # Inso 13.3.1's bail path exits zero before saveReport().
        if not (
            options.bail
            and not options.verbose
            and returncode == 0
            and report.failed_count
            and not report.run_error
        ):
            report.run_error = RunError(
                kind="protocol",
                message=(
                    "Inso did not write its native report. Check the export path, "
                    "collection identifier, and selected environment."
                ),
            )

    def _timeout_report(
        self, error: subprocess.TimeoutExpired, options, native_path: Path | None
    ) -> InsoRunReport:
        stdout, stderr = self._text(error.output), self._text(error.stderr)
        if native_path is not None and native_path.exists():
            report = self._native_report(native_path, options)
            if (
                report.run_error
                and report.run_error.kind == "protocol"
                and not options.verbose
            ):
                report = TapParser().parse(stdout, require_tap=True)
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
        report.raw_output = stdout + stderr
        return report

    def _execute(
        self,
        cmd: list[str],
        options,
        run_type: RunType,
        native_path: Path | None = None,
    ) -> InsoRunReport:
        started = time.monotonic()
        try:
            result = self._run_command(cmd, options.execution_timeout)
        except _OutputLimitError as error:
            report = (
                self._native_report(native_path, options)
                if native_path is not None and native_path.exists()
                else InsoRunReport(plan_end=0)
            )
            report.complete = False
            report.run_error = RunError(kind="execution", message=str(error))
        except subprocess.TimeoutExpired as error:
            report = self._timeout_report(error, options, native_path)
        else:
            report = self._completed_report(result, options, run_type, native_path)
            report.raw_output = result.stdout + result.stderr
        report.duration_seconds = time.monotonic() - started
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
            raise InsoConfigurationError(
                "Native collection reporting is required for verbose or response header capture. "
                "Use an Inso version with --output support, or disable --verbose and "
                "--capture-response-headers."
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
            raise InsoConfigurationError(
                "Legacy run-test does not support --verbose because script logs can spoof TAP results."
            )
        cmd = self._base_cmd(RunType.TEST, options.working_dir)
        self._apply_common_options(cmd, options)
        self._apply_test_options(cmd, options)
        if options.identifier:
            cmd.extend(["--", options.identifier])

        return self._execute(cmd, options, RunType.TEST)
