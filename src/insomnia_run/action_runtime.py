"""Composite-action adapter. Report files, not process streams, are authoritative."""

import os
from pathlib import Path
import secrets
import tempfile

import typer

from .models import InsoCollectionOptions, InsoRunReport, InsoTestOptions
from .native import validate_capture_headers
from .runner import InsoRunner

_JSON_REPORT = "report.json"
_MARKDOWN_REPORT = "report.md"
_JUNIT_REPORT = "junit.xml"
_RAW_REPORT = "raw.txt"
_REPORT_FILES = (_JUNIT_REPORT, _JSON_REPORT, _MARKDOWN_REPORT, _RAW_REPORT)


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def convenience_json(payload: str, *, requested: bool) -> tuple[str, bool]:
    if not requested:
        return "", False
    if len(payload.encode("utf-16-le")) > 64 * 1024:
        return "", True
    return payload, False


def write_outputs(path: Path, values: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as output:
        for key, value in values.items():
            delimiter = secrets.token_hex(32)
            while delimiter in value:
                delimiter = secrets.token_hex(32)
            output.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")


_COMMON = {
    "IDENTIFIER": "identifier",
    "ENVIRONMENT": "environment",
    "REQUEST_TIMEOUT": "request_timeout",
    "EXECUTION_TIMEOUT": "execution_timeout",
    "INPUT_HTTPS_PROXY": "https_proxy",
    "INPUT_HTTP_PROXY": "http_proxy",
    "INPUT_NO_PROXY": "no_proxy",
}
_COLLECTION = {
    "REQUEST_NAME_PATTERN": "request_name_pattern",
    "GLOBALS": "globals",
    "DELAY_REQUEST": "delay_request",
    "ITERATION_COUNT": "iteration_count",
    "ITERATION_DATA": "iteration_data",
}
_BOOLEAN_INPUTS = (
    "BAIL",
    "DISABLE_CERT_VALIDATION",
    "VERBOSE",
    "PROGRESS",
    "ANNOTATIONS",
    "KEEP_FILE",
    "INCLUDE_RAW_OUTPUT",
    "JUNIT_REPORT",
    "UPLOAD_ARTIFACT",
)


def _validate_inputs(env: dict[str, str]) -> None:
    command = env.get("COMMAND", "collection")
    if command not in {"collection", "test"}:
        raise ValueError("Invalid command. Must be collection or test.")
    output_format = env.get("OUTPUT_FORMAT", "").lower()
    if output_format not in {"", "json"}:
        raise ValueError("Invalid output format. Only json is supported.")
    for variable in _BOOLEAN_INPUTS:
        if env.get(variable, "").lower() not in {"", "true", "false"}:
            raise ValueError(
                f"{variable.lower().replace('_', '-')} must be true or false."
            )
    incompatible = (
        (*_COLLECTION, "ENV_VAR", "ITEM", "CAPTURE_RESPONSE_HEADERS")
        if command == "test"
        else ("TEST_NAME_PATTERN",)
    )
    if any(env.get(variable) for variable in incompatible) or (
        command == "collection" and env.get("KEEP_FILE", "").lower() == "true"
    ):
        raise ValueError("Input is not supported by the selected command.")


def _action_options(env: dict[str, str]) -> InsoCollectionOptions | InsoTestOptions:
    command = env.get("COMMAND", "collection")
    valued = {
        **_COMMON,
        **(
            _COLLECTION
            if command == "collection"
            else {"TEST_NAME_PATTERN": "test_name_pattern"}
        ),
    }
    values: dict[str, object] = {
        field: env[variable] for variable, field in valued.items() if env.get(variable)
    }
    values.update(
        working_dir=env.get("WORKING_DIR", ""),
        data_folders=split_list(env.get("DATA_FOLDERS", "")),
        **{
            key.lower(): env.get(key, "").lower() == "true"
            for key in ("BAIL", "DISABLE_CERT_VALIDATION", "VERBOSE")
        },
    )
    if command == "collection":
        pairs = [pair for pair in env.get("ENV_VAR", "").splitlines() if pair]
        if any("=" not in pair for pair in pairs):
            raise ValueError("Invalid env-var format. Expected KEY=VALUE.")
        values.update(
            env_var=pairs,
            item=split_list(env.get("ITEM", "")),
            capture_response_headers=validate_capture_headers(
                split_list(env.get("CAPTURE_RESPONSE_HEADERS", ""))
            ),
        )
        return InsoCollectionOptions.model_validate(values)
    values["keep_file"] = env.get("KEEP_FILE", "").lower() == "true"
    return InsoTestOptions.model_validate(values)


def _run_reports(
    env: dict[str, str],
    report_dir: Path,
    options: InsoCollectionOptions | InsoTestOptions,
) -> int:
    from .main import _execute_report, _finalize_report, _report_redactor

    raw = env.get("INCLUDE_RAW_OUTPUT", "").lower() == "true"
    redactor = _report_redactor(
        env.get("REDACT_VALUES", "").splitlines(),
        env_vars=options.env_var
        if isinstance(options, InsoCollectionOptions)
        else None,
        proxies=(options.http_proxy, options.https_proxy),
    )
    try:
        runner = InsoRunner(
            verified_version=env.get("INSOMNIA_RUN_INSO_VERSION"), redactor=redactor
        )
        report = _execute_report(
            lambda: (
                runner.run_collection(options)
                if isinstance(options, InsoCollectionOptions)
                else runner.run_test(options)
            ),
            progress=env.get("PROGRESS", "").lower() == "true",
            json_stderr=False,
        )
        _finalize_report(
            report,
            workflow_url=env.get("WORKFLOW_URL"),
            trusted_workflow_url=True,
            include_raw_output=raw,
            output_format=None,
            emit_markdown=False,
            destinations={
                "JSON": str(report_dir / _JSON_REPORT),
                "Markdown": str(report_dir / _MARKDOWN_REPORT),
                "JUnit": str(report_dir / _JUNIT_REPORT)
                if env.get("JUNIT_REPORT", "true").lower() == "true"
                else None,
                "raw": str(report_dir / _RAW_REPORT) if raw else None,
            },
            redactor=redactor,
            annotations=env.get("ANNOTATIONS", "").lower() == "true",
        )
    except typer.Exit as error:
        return error.exit_code
    except typer.BadParameter as error:
        print(f"::error::{error}")
        return 2
    return 0


def _artifact_options_valid(env: dict[str, str]) -> bool:
    if env.get("UPLOAD_ARTIFACT", "").lower() == "true":
        from .publication import artifact_upload_supported

        if not artifact_upload_supported(env.get("GITHUB_SERVER_URL", "")):
            print(
                "::error::Built-in artifact uploads support GitHub.com and GitHub Enterprise Cloud only. Use report files with a GHES uploader."
            )
            return False
        retention = env.get("ARTIFACT_RETENTION_DAYS", "14")
        if (
            not retention.isascii()
            or not retention.isdigit()
            or not 1 <= int(retention) <= 400
        ):
            print(
                "::error::artifact-retention-days must be between 1 and 400 within repository policy."
            )
            return False
    return True


def _read_action_report(
    env: dict[str, str], report_dir: Path, code: int
) -> tuple[InsoRunReport | None, str, str, int]:
    report = None
    payload = ""
    json_file, markdown_file = report_dir / _JSON_REPORT, report_dir / _MARKDOWN_REPORT
    if json_file.is_file():
        try:
            payload = json_file.read_text(encoding="utf-8")
            report = InsoRunReport.model_validate_json(payload)
        except (ValueError, OSError):
            code = 2
    else:
        code = code if code >= 2 else 2
    markdown = (
        markdown_file.read_text(encoding="utf-8") if markdown_file.is_file() else ""
    )
    required_files = [markdown_file]
    if env.get("JUNIT_REPORT", "true").lower() == "true":
        required_files.append(report_dir / _JUNIT_REPORT)
    if env.get("INCLUDE_RAW_OUTPUT", "").lower() == "true":
        required_files.append(report_dir / _RAW_REPORT)
    if any(not path.is_file() for path in required_files):
        code = code if code >= 2 else 2
    if report is not None and code in {0, 1} and report.exit_code != code:
        code = 2
    if report is None:
        markdown = ""
    return report, payload, markdown, code


def _copy_junit_report(
    env: dict[str, str], report_dir: Path, report: InsoRunReport | None, code: int
) -> tuple[Path, int]:
    junit = report_dir / _JUNIT_REPORT
    if (
        env.get("JUNIT_REPORT", "true").lower() == "true"
        and junit.is_file()
        and report
        and env.get("JUNIT_OUTPUT_FILE")
    ):
        from .report_files import write_report_file

        try:
            junit = write_report_file(
                env["JUNIT_OUTPUT_FILE"],
                junit.read_text(encoding="utf-8"),
                environ=env,
                other_paths=[report_dir / name for name in _REPORT_FILES],
            )
        except (OSError, ValueError):
            print(
                "::error::Unable to copy the JUnit report to the requested destination."
            )
            code = 2
    return junit, code


def _report_outputs(
    env: dict[str, str],
    report_dir: Path,
    report: InsoRunReport | None,
    junit: Path,
) -> dict[str, str]:
    outputs = {
        "report-directory": "",
        "json-file": "",
        "junit-file": "",
        "raw-file": "",
        "total": "",
        "passed": "",
        "failed": "",
        "skipped": "",
        "requests": "",
        "run-error": "",
        "complete": "",
    }
    if not report:
        return outputs
    outputs.update(
        {
            "report-directory": str(report_dir),
            "json-file": str(report_dir / _JSON_REPORT),
            "total": str(report.total_tests),
            "passed": str(report.passed_count),
            "failed": str(report.failed_count),
            "skipped": str(report.skipped_count),
            "requests": str(report.request_count)
            if report.request_count is not None
            else "",
            "run-error": str(bool(report.run_error)).lower(),
            "complete": str(report.complete).lower(),
        }
    )
    if env.get("JUNIT_REPORT", "true").lower() == "true" and junit.is_file():
        outputs["junit-file"] = str(junit)
    if (report_dir / _RAW_REPORT).is_file():
        outputs["raw-file"] = str(report_dir / _RAW_REPORT)
    return outputs


def run_action(env: dict[str, str]) -> int:
    if env.get("GITHUB_ACTIONS", "").lower() == "true":
        from .privacy import Redactor, mask_commands

        secrets_to_mask = Redactor(
            values=env.get("REDACT_VALUES", "").splitlines(),
            env_vars=env.get("ENV_VAR", "").splitlines(),
        ).values
        for command in mask_commands(secrets_to_mask):
            print(command, flush=True)
    try:
        _validate_inputs(env)
    except ValueError as error:
        print(f"::error::{error}")
        return 2
    if not _artifact_options_valid(env):
        return 2
    report_dir = Path(
        tempfile.mkdtemp(prefix="insomnia-run-reports.", dir=env["RUNNER_TEMP"])
    )
    try:
        options = _action_options(env)
    except ValueError:
        print("::error::Invalid Inso configuration. Check command options.")
        return 2
    try:
        if (
            env.get("JUNIT_OUTPUT_FILE")
            and env.get("JUNIT_REPORT", "true").lower() == "true"
        ):
            from .report_files import validate_destination

            validate_destination(
                env["JUNIT_OUTPUT_FILE"],
                environ=env,
                other_paths=[report_dir / name for name in _REPORT_FILES],
            )
    except ValueError as error:
        print(f"::error::{error}")
        return 2
    code = _run_reports(env, report_dir, options)
    report, payload, markdown, code = _read_action_report(env, report_dir, code)
    json_value, omitted = convenience_json(
        payload if report else "",
        requested=env.get("OUTPUT_FORMAT", "").lower() == "json",
    )
    junit, code = _copy_junit_report(env, report_dir, report, code)
    outputs = {
        "exit-code": str(code),
        "markdown": markdown,
        "json-output": json_value,
        "json-output-omitted": str(omitted).lower(),
        **_report_outputs(env, report_dir, report, junit),
    }
    write_outputs(Path(env["GITHUB_OUTPUT"]), outputs)
    with Path(env["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write(markdown)
    return 0


def main() -> None:
    try:
        raise SystemExit(run_action(dict(os.environ)))
    except (OSError, ValueError):
        print(
            "::error::Unable to execute or publish report files. Check runner paths and permissions."
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
