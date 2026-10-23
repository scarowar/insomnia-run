import importlib.metadata
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
import threading
import time
from urllib.parse import unquote, urlsplit
import typer
from typing import Annotated, Optional

from .models import InsoCollectionOptions, InsoRunReport, InsoStatus, InsoTestOptions
from .native import validate_capture_headers
from .privacy import Redactor
from .publication import failure_annotations
from .report_files import validate_destination, write_report_file
from .runner import InsoConfigurationError, InsoRunner
from .reporter import Reporter

app = typer.Typer(
    name="insomnia-run",
    help="CLI runner for Insomnia API tests and collections.",
    pretty_exceptions_show_locals=False,
)

SUPPORTED_OUTPUT_FORMATS = {"json"}
_PROGRESS_INTERVAL_SECONDS = 15

_WorkingDirOption = Annotated[
    str,
    typer.Option(
        "--working-dir",
        "-w",
        help="Path to an Insomnia export, legacy Git Sync repository root, or app-data directory",
    ),
]
_EnvironmentOption = Annotated[
    Optional[str], typer.Option("--env", "-e", help="Environment name to use")
]
_RequestTimeoutOption = Annotated[
    Optional[int], typer.Option("--request-timeout", min=0, help="Request timeout (ms)")
]
_BailOption = Annotated[
    bool, typer.Option("--bail", "-b", help="Stop on first failure")
]
_DisableCertValidationOption = Annotated[
    bool,
    typer.Option("--disable-cert-validation", "-k", help="Disable SSL verification"),
]
_HttpsProxyOption = Annotated[
    Optional[str], typer.Option("--https-proxy", help="HTTPS proxy URL")
]
_HttpProxyOption = Annotated[
    Optional[str], typer.Option("--http-proxy", help="HTTP proxy URL")
]
_NoProxyOption = Annotated[
    Optional[str], typer.Option("--no-proxy", help="Hosts to bypass proxy")
]
_VerboseOption = Annotated[bool, typer.Option("--verbose", help="Show additional logs")]
_ExecutionTimeoutOption = Annotated[
    int,
    typer.Option(
        "--execution-timeout",
        min=1,
        help="Execution timeout for the entire process (seconds)",
    ),
]
_WorkflowUrlOption = Annotated[
    Optional[str],
    typer.Option("--workflow-url", help="GitHub workflow URL for report links"),
]
_OutputFormatOption = Annotated[
    Optional[str],
    typer.Option(
        "--output-format",
        help="The format to use for the report output (e.g., 'json').",
    ),
]
_IncludeRawOutputOption = Annotated[
    bool,
    typer.Option(
        "--include-raw-output",
        help="Include raw Inso output in Markdown and JSON reports.",
    ),
]
_JunitOutputOption = Annotated[
    Optional[str],
    typer.Option("--junit-output", help="Write a JUnit XML report to this path."),
]
_JsonOutputOption = Annotated[
    Optional[str],
    typer.Option("--json-output", help="Write a normalized JSON report to this path."),
]
_MarkdownOutputOption = Annotated[
    Optional[str],
    typer.Option("--markdown-output", help="Write a Markdown report to this path."),
]
_RawOutputFileOption = Annotated[
    Optional[str],
    typer.Option(
        "--raw-output-file", help="Write redacted raw Inso output to this path."
    ),
]
_RedactValueOption = Annotated[
    Optional[list[str]],
    typer.Option("--redact-value", help="Additional value to redact (repeatable)."),
]
_ProgressOption = Annotated[
    bool,
    typer.Option(
        "--progress", help="Show execution stages and elapsed-time heartbeats."
    ),
]
_AnnotationsOption = Annotated[
    bool, typer.Option("--annotations", help="Emit bounded GitHub failure annotations.")
]


def _get_version() -> str:
    try:
        return importlib.metadata.version("insomnia-run")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _validate_output_format(output_format: Optional[str]) -> None:
    if not output_format:
        return

    requested_format = output_format.lower()
    if requested_format not in SUPPORTED_OUTPUT_FORMATS:
        raise typer.BadParameter(
            f"Unsupported output format: '{output_format}'. Currently supported: json"
        )


def _emit_machine_readable_output(
    report, output_format: Optional[str], *, include_raw_output: bool = False
) -> None:
    """Emit JSON to stderr, leaving stdout for Markdown."""
    if not output_format:
        return

    _validate_output_format(output_format)
    requested_format = output_format.lower()

    if requested_format == "json":
        json_report = report.model_dump_json(
            indent=2, exclude=None if include_raw_output else {"raw_output"}
        )
        typer.echo(json_report, err=True)


def _validate_report_destinations(destinations: dict[str, Optional[str]]) -> None:
    for name, path in destinations.items():
        if path is None:
            continue
        others = [
            other
            for other_name, other in destinations.items()
            if other_name != name and other is not None
        ]
        try:
            validate_destination(path, other_paths=others)
        except (OSError, ValueError) as error:
            raise typer.BadParameter(
                f"Unable to write {name} report. Check destination paths and permissions."
            ) from error


@contextmanager
def _execution_progress(enabled: bool, *, err: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    started = time.monotonic()
    stopped = threading.Event()

    def heartbeat() -> None:
        while not stopped.wait(_PROGRESS_INTERVAL_SECONDS):
            typer.echo(
                f"Inso is running ({int(time.monotonic() - started)}s elapsed).",
                err=err,
            )

    typer.echo("Starting Inso execution.", err=err)
    worker = threading.Thread(target=heartbeat, name="insomnia-progress", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stopped.set()
        worker.join()
        typer.echo(
            f"Inso execution finished ({int(time.monotonic() - started)}s elapsed).",
            err=err,
        )


def _execute_report(
    operation: Callable[[], InsoRunReport], *, progress: bool, json_stderr: bool
) -> InsoRunReport:
    try:
        with _execution_progress(progress, err=not json_stderr):
            return operation()
    except OSError as error:
        typer.echo(
            "Unable to execute Inso CLI. Check installation and executable permissions.",
            err=True,
        )
        raise typer.Exit(code=2) from error
    except InsoConfigurationError as error:
        raise typer.BadParameter(str(error)) from error
    except ValueError as error:
        raise typer.BadParameter(
            "Invalid Inso configuration. Check command options."
        ) from error


def _report_redactor(
    values: Optional[list[str]],
    *,
    env_vars: list[str] | Mapping[str, str] | None = None,
    proxies: tuple[Optional[str], ...] = (),
) -> Redactor:
    secrets = list(values or [])
    proxies += tuple(
        os.environ.get(name)
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
    )
    for proxy in proxies:
        if not proxy:
            continue
        try:
            parsed = urlsplit(proxy)
            secrets.extend(
                unquote(value) for value in (parsed.username, parsed.password) if value
            )
        except ValueError:
            continue
    return Redactor(values=secrets, env_vars=env_vars)


def _finalize_report(
    report: InsoRunReport,
    *,
    workflow_url: Optional[str],
    include_raw_output: bool,
    output_format: Optional[str],
    destinations: dict[str, Optional[str]],
    redactor: Redactor,
    annotations: bool,
    emit_markdown: bool = True,
    trusted_workflow_url: bool = False,
) -> None:
    reporter = Reporter()
    if not include_raw_output and not destinations.get("raw"):
        report = report.model_copy(update={"raw_output": None})
    report = redactor.redact_report(report)
    if report.raw_output:
        # Redact complete values before a byte boundary can split a credential.
        report.raw_output = report.raw_output.encode("utf-8")[-1024 * 1024 :].decode(
            "utf-8", errors="ignore"
        )
    _emit_machine_readable_output(
        report, output_format, include_raw_output=include_raw_output
    )
    write_failed = False
    if workflow_url and not trusted_workflow_url:
        workflow_url = redactor.redact(workflow_url)
    try:
        markdown = reporter.generate_markdown(
            report,
            workflow_url=workflow_url,
            include_raw_output=include_raw_output,
        )
    except (OSError, ValueError):
        markdown = "Unable to generate Markdown report."
        write_failed = True
    if emit_markdown:
        typer.echo(markdown, nl=False)
    serializers: dict[str, Callable[[], str]] = {
        "JUnit": lambda: reporter.generate_junit(report),
        "JSON": lambda: (
            report.model_dump_json(
                indent=2, exclude=None if include_raw_output else {"raw_output"}
            )
            + "\n"
        ),
        "Markdown": lambda: markdown,
        "raw": lambda: report.raw_output or "",
    }
    files_failed = _write_report_files(
        destinations, serializers, json_stderr=bool(output_format)
    )
    if annotations:
        _emit_annotations(report, err=not bool(output_format))
    if write_failed or files_failed:
        raise typer.Exit(code=2)
    if report.exit_code:
        raise typer.Exit(code=report.exit_code)


def _write_report_files(
    destinations: dict[str, Optional[str]],
    serializers: dict[str, Callable[[], str]],
    *,
    json_stderr: bool,
) -> bool:
    write_failed = False
    for name, path in destinations.items():
        if path is None:
            continue
        try:
            write_report_file(
                path,
                serializers[name](),
                other_paths=[
                    other
                    for other_name, other in destinations.items()
                    if other_name != name and other is not None
                ],
            )
        except (OSError, ValueError):
            typer.echo(
                f"Unable to write {name} report. Check destination paths and permissions.",
                err=not json_stderr,
            )
            write_failed = True
    return write_failed


def _emit_annotations(report: InsoRunReport, *, err: bool) -> None:
    messages = [report.run_error.message] if report.run_error else []
    contexts = {}
    for execution in report.executions:
        label = execution.name
        if execution.iteration is not None:
            label += f" / Iteration {execution.iteration + 1}"
        contexts[execution.id] = label
    for result in report.results:
        if result.status != InsoStatus.FAIL:
            continue
        message = (
            f"{result.description}: {result.message}"
            if result.message
            else result.description
        )
        if result.execution_id in contexts:
            message = f"{contexts[result.execution_id]}: {message}"
        messages.append(message)
    for command in failure_annotations(messages):
        typer.echo(command, err=err)


@app.callback(invoke_without_command=True)
def version_callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show the insomnia-run version and exit.",
        is_eager=True,
    ),
):
    """Global options."""
    if version:
        typer.echo(f"insomnia-run {_get_version()}")
        raise typer.Exit()


@app.command()
def run_collection(  # NOSONAR - CLI command requires many options
    working_dir: _WorkingDirOption,
    identifier: Optional[str] = typer.Option(
        None, "--identifier", "-i", help="Collection name or workspace ID"
    ),
    environment: _EnvironmentOption = None,
    request_name_pattern: Optional[str] = typer.Option(
        None, "--request-name-pattern", help="Regex to filter requests"
    ),
    item: Optional[list[str]] = typer.Option(
        None, "--item", help="Request or folder IDs to run (repeatable)"
    ),
    globals: Optional[str] = typer.Option(
        None, "--globals", "-g", help="Global environment file, ID, or name"
    ),
    delay_request: Optional[int] = typer.Option(
        None, "--delay-request", min=0, help="Delay between requests (ms)"
    ),
    request_timeout: _RequestTimeoutOption = None,
    iteration_count: Optional[int] = typer.Option(
        None, "--iteration-count", "-n", min=1, help="Number of iterations"
    ),
    iteration_data: Optional[str] = typer.Option(
        None,
        "--iteration-data",
        "-d",
        help="CSV/JSON iteration data path or HTTP(S) URL",
    ),
    env_var: Optional[list[str]] = typer.Option(
        None,
        "--env-var",
        help="Override env vars (KEY=VALUE, repeatable; Inso URL decoding)",
    ),
    bail: _BailOption = False,
    disable_cert_validation: _DisableCertValidationOption = False,
    https_proxy: _HttpsProxyOption = None,
    http_proxy: _HttpProxyOption = None,
    no_proxy: _NoProxyOption = None,
    data_folders: Optional[list[str]] = typer.Option(
        None, "--data-folders", "-f", help="Folders Insomnia can access (repeatable)"
    ),
    verbose: _VerboseOption = False,
    execution_timeout: _ExecutionTimeoutOption = 300,
    workflow_url: _WorkflowUrlOption = None,
    output_format: _OutputFormatOption = None,
    include_raw_output: _IncludeRawOutputOption = False,
    junit_output: _JunitOutputOption = None,
    json_output: _JsonOutputOption = None,
    markdown_output: _MarkdownOutputOption = None,
    raw_output_file: _RawOutputFileOption = None,
    redact_value: _RedactValueOption = None,
    capture_response_headers: Optional[str] = typer.Option(
        None,
        "--capture-response-headers",
        help="Comma-separated response header names to retain.",
    ),
    progress: _ProgressOption = False,
    annotations: _AnnotationsOption = False,
):
    """Run Insomnia collections and generate a markdown report."""

    _validate_output_format(output_format)
    destinations = {
        "JUnit": junit_output,
        "JSON": json_output,
        "Markdown": markdown_output,
        "raw": raw_output_file,
    }
    _validate_report_destinations(destinations)

    if env_var:
        for pair in env_var:
            if "=" not in pair:
                raise typer.BadParameter("Invalid env-var format. Expected KEY=VALUE.")

    try:
        headers = validate_capture_headers(
            capture_response_headers.split(",")
            if capture_response_headers and capture_response_headers.strip()
            else []
        )
    except ValueError as error:
        raise typer.BadParameter(
            "Response header names must be explicit and non-credential-bearing."
        ) from error

    options = InsoCollectionOptions(
        working_dir=working_dir,
        identifier=identifier,
        environment=environment,
        request_name_pattern=request_name_pattern,
        item=item,
        globals=globals,
        delay_request=delay_request,
        request_timeout=request_timeout,
        iteration_count=iteration_count,
        iteration_data=iteration_data,
        env_var=env_var,
        bail=bail,
        disable_cert_validation=disable_cert_validation,
        https_proxy=https_proxy,
        http_proxy=http_proxy,
        no_proxy=no_proxy,
        data_folders=data_folders,
        verbose=verbose,
        execution_timeout=execution_timeout,
        capture_response_headers=headers,
    )

    redactor = _report_redactor(
        redact_value, env_vars=env_var, proxies=(http_proxy, https_proxy)
    )
    runner = InsoRunner(redactor=redactor)
    report = _execute_report(
        lambda: runner.run_collection(options),
        progress=progress,
        json_stderr=bool(output_format),
    )

    _finalize_report(
        report,
        workflow_url=workflow_url,
        include_raw_output=include_raw_output,
        output_format=output_format,
        destinations=destinations,
        redactor=redactor,
        annotations=annotations,
    )


@app.command()
def run_test(  # NOSONAR - CLI command requires many options
    working_dir: _WorkingDirOption,
    identifier: Optional[str] = typer.Option(
        None, "--identifier", "-i", help="Test suite or API spec ID"
    ),
    environment: _EnvironmentOption = None,
    test_name_pattern: Optional[str] = typer.Option(
        None,
        "--test-name-pattern",
        "-t",
        help="Literal substring to filter test titles (Inso 13.3.1)",
    ),
    bail: _BailOption = False,
    keep_file: bool = typer.Option(
        False, "--keep-file", help="Keep generated test file"
    ),
    request_timeout: _RequestTimeoutOption = None,
    disable_cert_validation: _DisableCertValidationOption = False,
    https_proxy: _HttpsProxyOption = None,
    http_proxy: _HttpProxyOption = None,
    no_proxy: _NoProxyOption = None,
    data_folders: Optional[list[str]] = typer.Option(
        None, "--data-folders", "-f", help="Folders Insomnia can access"
    ),
    verbose: _VerboseOption = False,
    execution_timeout: _ExecutionTimeoutOption = 300,
    workflow_url: _WorkflowUrlOption = None,
    output_format: _OutputFormatOption = None,
    include_raw_output: _IncludeRawOutputOption = False,
    junit_output: _JunitOutputOption = None,
    json_output: _JsonOutputOption = None,
    markdown_output: _MarkdownOutputOption = None,
    raw_output_file: _RawOutputFileOption = None,
    redact_value: _RedactValueOption = None,
    progress: _ProgressOption = False,
    annotations: _AnnotationsOption = False,
):
    """Run Insomnia unit tests and generate a markdown report."""

    _validate_output_format(output_format)
    destinations = {
        "JUnit": junit_output,
        "JSON": json_output,
        "Markdown": markdown_output,
        "raw": raw_output_file,
    }
    _validate_report_destinations(destinations)
    if verbose:
        raise typer.BadParameter(
            "Legacy run-test does not support --verbose because script logs can spoof TAP results."
        )

    options = InsoTestOptions(
        working_dir=working_dir,
        identifier=identifier,
        environment=environment,
        test_name_pattern=test_name_pattern,
        bail=bail,
        keep_file=keep_file,
        request_timeout=request_timeout,
        disable_cert_validation=disable_cert_validation,
        https_proxy=https_proxy,
        http_proxy=http_proxy,
        no_proxy=no_proxy,
        data_folders=data_folders,
        verbose=verbose,
        execution_timeout=execution_timeout,
    )

    redactor = _report_redactor(redact_value, proxies=(http_proxy, https_proxy))
    runner = InsoRunner(redactor=redactor)
    report = _execute_report(
        lambda: runner.run_test(options),
        progress=progress,
        json_stderr=bool(output_format),
    )

    _finalize_report(
        report,
        workflow_url=workflow_url,
        include_raw_output=include_raw_output,
        output_format=output_format,
        destinations=destinations,
        redactor=redactor,
        annotations=annotations,
    )


def main():
    app()


if __name__ == "__main__":
    main()
