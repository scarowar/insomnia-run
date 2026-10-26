import importlib.metadata
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
import threading
import time
from urllib.parse import unquote, urlsplit
import typer
from typing import Optional
from dataclasses import fields

from .cli_options import CollectionCommand, ReportOptions, TestCommand

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
    report = report.model_copy(update={"run_error": report.evidence_error})
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


def _collection_options(arguments: dict) -> InsoCollectionOptions:
    for pair in arguments.get("env_var") or []:
        if "=" not in pair:
            raise typer.BadParameter("Invalid env-var format. Expected KEY=VALUE.")
    raw_headers = arguments.pop("capture_response_headers")
    try:
        arguments["capture_response_headers"] = validate_capture_headers(
            raw_headers.split(",") if raw_headers and raw_headers.strip() else []
        )
    except ValueError as error:
        raise typer.BadParameter(
            "Response header names must be explicit and non-credential-bearing."
        ) from error
    return InsoCollectionOptions(**arguments)


def _run_cli(ctx: typer.Context, *, collection: bool) -> None:
    arguments = dict(ctx.meta["run_options"])
    reporting = ReportOptions(
        **{field.name: arguments.pop(field.name) for field in fields(ReportOptions)}
    )
    _validate_output_format(reporting.output_format)
    _validate_report_destinations(reporting.destinations)
    options: InsoCollectionOptions | InsoTestOptions
    if collection:
        options = _collection_options(arguments)
    else:
        if arguments["verbose"]:
            raise typer.BadParameter(
                "Legacy run-test does not support --verbose because script logs can spoof TAP results."
            )
        options = InsoTestOptions(**arguments)
    redactor = _report_redactor(
        reporting.redact_value,
        env_vars=options.env_var
        if isinstance(options, InsoCollectionOptions)
        else None,
        proxies=(options.http_proxy, options.https_proxy),
    )
    runner = InsoRunner(redactor=redactor)
    report = _execute_report(
        lambda: (
            runner.run_collection(options)
            if isinstance(options, InsoCollectionOptions)
            else runner.run_test(options)
        ),
        progress=reporting.progress,
        json_stderr=bool(reporting.output_format),
    )
    _finalize_report(
        report,
        workflow_url=reporting.workflow_url,
        include_raw_output=reporting.include_raw_output,
        output_format=reporting.output_format,
        destinations=reporting.destinations,
        redactor=redactor,
        annotations=reporting.annotations,
    )


@app.command(cls=CollectionCommand)
def run_collection(ctx: typer.Context):
    """Run Insomnia collections and generate a markdown report."""
    _run_cli(ctx, collection=True)


@app.command(cls=TestCommand)
def run_test(ctx: typer.Context):
    """Run Insomnia unit tests and generate a markdown report."""
    _run_cli(ctx, collection=False)


def main():
    app()


if __name__ == "__main__":
    main()
