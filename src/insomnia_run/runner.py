import os
import re
import subprocess
import sys

from .models import (
    InsoCollectionOptions,
    InsoResult,
    InsoRunReport,
    InsoStatus,
    InsoTestOptions,
    RunType,
)
from .parser import TapParser

_REDACTED = "***REDACTED***"
_MAX_ERROR_LENGTH = 4000
_MIN_SECRET_LENGTH = 4
_TOKENIZED_URL_RE = re.compile(
    r"(?i)(https?://[^\s]*?(?:token|access[_-]?token|api[_-]?key|api[_-]?secret|"
    r"client[_-]?secret|password|passwd|secret|signature|sig|key)="
    r")[^\s&]+"
)
_SECRET_HEADER_RE = re.compile(
    r'(?i)(["\']?[A-Za-z0-9-]*(?:authorization|api[_-]?key|x-api-key|cookie)'
    r'["\']?\s*:\s*)["\']?\S.*$',
    re.MULTILINE,
)


class InsoRunner:
    @staticmethod
    def _base_cmd(run_type: RunType, working_dir: str, identifier: str | None):
        cmd = ["inso", "run", run_type.value]

        if identifier:
            cmd.append(identifier)

        cmd.extend(["-w", working_dir, "--reporter", "tap", "--ci"])
        return cmd

    @staticmethod
    def _apply_common_options(cmd: list[str], options: InsoCollectionOptions | InsoTestOptions):
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

        if options.bail:
            cmd.append("--bail")

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

    @staticmethod
    def _apply_test_options(cmd: list[str], options: InsoTestOptions):
        if options.test_name_pattern:
            cmd.extend(["--testNamePattern", options.test_name_pattern])

        if options.keep_file:
            cmd.append("--keepFile")

    @staticmethod
    def _redact_output(raw: str, options: InsoCollectionOptions | InsoTestOptions) -> str:
        """Redact known secrets from captured output.

        Applied once at capture time so every downstream consumer (markdown,
        JUnit, annotations, artifacts) inherits the invariant for free.
        """
        if not raw:
            return raw

        out = raw

        env_var = getattr(options, "env_var", None)
        if env_var:
            secrets = sorted(
                (v for v in env_var.values() if v and len(v) >= _MIN_SECRET_LENGTH),
                key=len,
                reverse=True,
            )
            for secret in secrets:
                out = out.replace(secret, _REDACTED)

        out = _SECRET_HEADER_RE.sub(lambda m: m.group(1) + _REDACTED, out)
        out = _TOKENIZED_URL_RE.sub(lambda m: m.group(1) + _REDACTED, out)
        return out

    @staticmethod
    def _cap(text: str, limit: int = _MAX_ERROR_LENGTH) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + f"\n... (truncated, {len(text)} chars total)"

    def _timeout_report(
        self,
        exc: subprocess.TimeoutExpired,
        options: InsoCollectionOptions | InsoTestOptions,
        run_type: RunType,
    ) -> InsoRunReport:
        message = f"Inso CLI timed out after {options.execution_timeout} seconds"

        partial_stdout = self._coerce_output(exc.stdout)
        partial_stderr = self._coerce_output(exc.stderr)
        partial = self._redact_output(partial_stdout + partial_stderr, options).strip()

        report = InsoRunReport(
            plan_end=0,
            run_type=run_type,
            target_name=options.identifier,
            raw_output=f"{partial}\n{message}" if partial else message,
            diagnostics=[message],
        )
        report.results.append(
            InsoResult(
                id=1,
                status=InsoStatus.FAIL,
                description=f"Inso CLI Error: {message}",
            )
        )
        return report

    @staticmethod
    def _coerce_output(data: str | bytes | None) -> str:
        if data is None:
            return ""
        if isinstance(data, bytes):
            return data.decode(errors="replace")
        return data

    def run_collection(self, options: InsoCollectionOptions) -> InsoRunReport:
        return self._run(options, RunType.COLLECTION)

    def run_test(self, options: InsoTestOptions) -> InsoRunReport:
        return self._run(options, RunType.TEST)

    @staticmethod
    def _is_flag_like(value: str | None) -> bool:
        return bool(value and value.lstrip().startswith("-"))

    def _flag_error(
        self, field: str, value: str, run_type: RunType, identifier: str | None
    ) -> InsoRunReport:
        msg = f"Invalid {field} '{value}': must not start with '-'"
        report = InsoRunReport(
            plan_end=0,
            run_type=run_type,
            target_name=identifier,
            raw_output=msg,
            diagnostics=[msg],
        )
        report.results.append(InsoResult(id=1, status=InsoStatus.FAIL, description=msg))
        return report

    def _run(
        self, options: InsoCollectionOptions | InsoTestOptions, run_type: RunType
    ) -> InsoRunReport:
        for field, val in [
            ("identifier", options.identifier),
            ("environment", options.environment),
            ("working-directory", options.working_dir),
            ("globals", getattr(options, "globals", None)),
            ("iteration-data", getattr(options, "iteration_data", None)),
            ("request-name-pattern", getattr(options, "request_name_pattern", None)),
            ("test-name-pattern", getattr(options, "test_name_pattern", None)),
            ("https-proxy", options.https_proxy),
            ("http-proxy", options.http_proxy),
            ("no-proxy", options.no_proxy),
        ]:
            if self._is_flag_like(val):  # type: ignore[arg-type]
                return self._flag_error(field, val, run_type, options.identifier)  # type: ignore[arg-type]
        for fld, lst in [
            ("item", getattr(options, "item", None)),
            ("data-folders", options.data_folders),
        ]:
            if lst:
                for v in lst:
                    if self._is_flag_like(v):
                        return self._flag_error(fld, v, run_type, options.identifier)
        if getattr(options, "env_var", None):
            for k in options.env_var:  # type: ignore[union-attr]
                if self._is_flag_like(k):
                    return self._flag_error("env-var key", k, run_type, options.identifier)
        cmd = self._base_cmd(run_type, options.working_dir, options.identifier)
        self._apply_common_options(cmd, options)
        if isinstance(options, InsoCollectionOptions):
            self._apply_collection_options(cmd, options)
        else:
            self._apply_test_options(cmd, options)

        # Mask env-var secrets in Actions logs before argv is visible via ps
        env_var = getattr(options, "env_var", None)
        if env_var and os.environ.get("GITHUB_ACTIONS") == "true":
            for v in env_var.values():
                if v and len(v) >= _MIN_SECRET_LENGTH:
                    escaped = v.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
                    print(f"::add-mask::{escaped}", file=sys.stderr, flush=True)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=options.execution_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return self._timeout_report(exc, options, run_type)
        except (FileNotFoundError, PermissionError, OSError) as exc:
            hint = "Make sure Inso CLI is installed. The action installs it automatically on GitHub Actions."
            raw = self._cap(self._redact_output(str(exc), options))
            report = InsoRunReport(
                plan_end=0,
                run_type=run_type,
                target_name=options.identifier,
                raw_output=raw,
                diagnostics=[f"Could not execute Inso CLI: {exc}. {hint}"],
            )
            report.results.append(
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description=f"Could not execute Inso CLI: {exc}",
                )
            )
            return report

        redacted_stdout = self._redact_output(result.stdout, options)
        raw_output = self._redact_output(result.stdout + result.stderr, options)

        parser = TapParser()
        # Feed the parser the same redacted capture every other consumer sees;
        # harvested descriptions/messages must not bypass redaction.
        report = parser.parse(redacted_stdout, run_type)
        report.raw_output = raw_output
        report.run_type = run_type
        report.target_name = options.identifier

        if result.returncode != 0:
            stderr = self._cap(self._redact_output(result.stderr.strip(), options))
            if report.total_tests == 0:
                report.results.append(
                    InsoResult(
                        id=1,
                        status=InsoStatus.FAIL,
                        description=f"Inso CLI Error (exit code {result.returncode}): {stderr or 'Unknown error'}",
                    )
                )
            else:
                report.diagnostics.append(
                    f"Inso exited with code {result.returncode}: {stderr or 'Unknown error'}"
                )
        elif report.total_tests == 0:
            report.results.append(
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="No test results parsed from Inso output",
                )
            )
            report.diagnostics.append(
                "Inso reported success but no TAP test results were found in its output."
            )

        return report
