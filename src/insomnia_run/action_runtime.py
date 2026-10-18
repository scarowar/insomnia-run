"""Composite-action adapter. Report files, not process streams, are authoritative."""

import os
from pathlib import Path
import secrets
import subprocess  # nosec B404
import sys
import tempfile

from .models import InsoRunReport


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
    "IDENTIFIER": "--identifier",
    "ENVIRONMENT": "--env",
    "REQUEST_TIMEOUT": "--request-timeout",
    "EXECUTION_TIMEOUT": "--execution-timeout",
    "INPUT_HTTPS_PROXY": "--https-proxy",
    "INPUT_HTTP_PROXY": "--http-proxy",
    "INPUT_NO_PROXY": "--no-proxy",
    "WORKFLOW_URL": "--workflow-url",
}
_COLLECTION = {
    "REQUEST_NAME_PATTERN": "--request-name-pattern",
    "GLOBALS": "--globals",
    "DELAY_REQUEST": "--delay-request",
    "ITERATION_COUNT": "--iteration-count",
    "ITERATION_DATA": "--iteration-data",
    "CAPTURE_RESPONSE_HEADERS": "--capture-response-headers",
}


def command_args(env: dict[str, str], report_dir: Path) -> list[str]:
    command = env.get("COMMAND", "")
    if command not in {"collection", "test"}:
        raise ValueError("Invalid command. Must be collection or test.")
    output_format = env.get("OUTPUT_FORMAT", "").lower()
    if output_format not in {"", "json"}:
        raise ValueError("Invalid output format. Only json is supported.")
    args = [
        f"run-{command}",
        "--working-dir",
        env.get("WORKING_DIR", ""),
        "--json-output",
        str(report_dir / "report.json"),
        "--markdown-output",
        str(report_dir / "report.md"),
    ]
    valued = {
        **_COMMON,
        **(
            _COLLECTION
            if command == "collection"
            else {"TEST_NAME_PATTERN": "--test-name-pattern"}
        ),
    }
    for variable, option in valued.items():
        if env.get(variable):
            args.extend([option, env[variable]])
    for variable, option in {
        "BAIL": "--bail",
        "DISABLE_CERT_VALIDATION": "--disable-cert-validation",
        "VERBOSE": "--verbose",
        "PROGRESS": "--progress",
        "ANNOTATIONS": "--annotations",
    }.items():
        if env.get(variable, "").lower() == "true":
            args.append(option)
    if command == "test" and env.get("KEEP_FILE", "").lower() == "true":
        args.append("--keep-file")
    for variable, option in {
        "DATA_FOLDERS": "--data-folders",
        **({"ITEM": "--item"} if command == "collection" else {}),
    }.items():
        for item in split_list(env.get(variable, "")):
            args.extend([option, item])
    if command == "collection":
        for pair in env.get("ENV_VAR", "").splitlines():
            if pair:
                args.extend(["--env-var", pair])
    for value in env.get("REDACT_VALUES", "").splitlines():
        if value:
            args.extend(["--redact-value", value])
    if env.get("INCLUDE_RAW_OUTPUT", "").lower() == "true":
        args.extend(
            ["--include-raw-output", "--raw-output-file", str(report_dir / "raw.txt")]
        )
    if env.get("JUNIT_REPORT", "true").lower() == "true":
        args.extend(["--junit-output", str(report_dir / "junit.xml")])
    return args


def run_action(env: dict[str, str]) -> int:
    if env.get("GITHUB_ACTIONS", "").lower() == "true":
        from .privacy import Redactor, mask_commands

        secrets_to_mask = Redactor(
            values=env.get("REDACT_VALUES", "").splitlines(),
            env_vars=env.get("ENV_VAR", "").splitlines(),
        ).values
        for command in mask_commands(secrets_to_mask):
            print(command, flush=True)
    if env.get("UPLOAD_ARTIFACT", "").lower() == "true":
        from .publication import artifact_upload_supported

        if not artifact_upload_supported(env.get("GITHUB_SERVER_URL", "")):
            print(
                "::error::Built-in artifact uploads support GitHub.com and GitHub Enterprise Cloud only. Use report files with a GHES uploader."
            )
            return 2
        retention = env.get("ARTIFACT_RETENTION_DAYS", "14")
        if (
            not retention.isascii()
            or not retention.isdigit()
            or not 1 <= int(retention) <= 400
        ):
            print(
                "::error::artifact-retention-days must be between 1 and 400 within repository policy."
            )
            return 2
    report_dir = Path(
        tempfile.mkdtemp(prefix="insomnia-run-reports.", dir=env["RUNNER_TEMP"])
    )
    try:
        args = command_args(env, report_dir)
        if (
            env.get("JUNIT_OUTPUT_FILE")
            and env.get("JUNIT_REPORT", "true").lower() == "true"
        ):
            from .report_files import validate_destination

            validate_destination(
                env["JUNIT_OUTPUT_FILE"],
                environ=env,
                other_paths=[
                    report_dir / name
                    for name in ("junit.xml", "report.json", "report.md", "raw.txt")
                ],
            )
    except ValueError as error:
        print(f"::error::{error}")
        return 2
    # CLI stdout can contain untrusted names. Do not replay it as workflow commands.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as stdout:
        process = subprocess.run(  # nosec B603
            [sys.executable, "-m", "insomnia_run.main", *args],
            stdout=stdout,
            check=False,
            env=env,
        )
    code = process.returncode
    report = None
    json_file, markdown_file = report_dir / "report.json", report_dir / "report.md"
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
        required_files.append(report_dir / "junit.xml")
    if env.get("INCLUDE_RAW_OUTPUT", "").lower() == "true":
        required_files.append(report_dir / "raw.txt")
    if any(not path.is_file() for path in required_files):
        code = code if code >= 2 else 2
    if report is not None and code in {0, 1} and report.exit_code != code:
        code = 2
    if report is None:
        markdown = ""
    json_value, omitted = convenience_json(
        payload if report else "",
        requested=env.get("OUTPUT_FORMAT", "").lower() == "json",
    )
    junit = report_dir / "junit.xml"
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
                other_paths=[
                    report_dir / name
                    for name in ("junit.xml", "report.json", "report.md", "raw.txt")
                ],
            )
        except (OSError, ValueError):
            print(
                "::error::Unable to copy the JUnit report to the requested destination."
            )
            code = 2
    outputs = {
        "exit-code": str(code),
        "markdown": markdown,
        "json-output": json_value,
        "json-output-omitted": str(omitted).lower(),
        "report-directory": str(report_dir) if report else "",
        "json-file": str(json_file) if report else "",
        "junit-file": str(junit)
        if report
        and env.get("JUNIT_REPORT", "true").lower() == "true"
        and junit.is_file()
        else "",
        "raw-file": str(report_dir / "raw.txt")
        if report and (report_dir / "raw.txt").is_file()
        else "",
        "total": str(report.total_tests) if report else "",
        "passed": str(report.passed_count) if report else "",
        "failed": str(report.failed_count) if report else "",
        "skipped": str(report.skipped_count) if report else "",
        "requests": str(report.request_count)
        if report and report.request_count is not None
        else "",
        "run-error": str(bool(report.run_error)).lower() if report else "",
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
