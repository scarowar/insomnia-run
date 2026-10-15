import importlib.metadata
from pathlib import Path
import typer
from typing import Optional

from .models import InsoCollectionOptions, InsoTestOptions
from .runner import InsoRunner
from .reporter import Reporter

app = typer.Typer(
    name="insomnia-run",
    help="CLI runner for Insomnia API tests and collections.",
    pretty_exceptions_show_locals=False,
)

SUPPORTED_OUTPUT_FORMATS = {"json"}


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


def _write_junit_output(
    reporter: Reporter,
    report,
    junit_output: Optional[str],
) -> None:
    if not junit_output:
        return

    output_path = Path(junit_output)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(reporter.generate_junit(report), encoding="utf-8")
    except OSError as error:
        typer.echo(
            "Unable to write JUnit report. Check the destination path and permissions.",
            err=True,
        )
        raise typer.Exit(code=2) from error


def _finalize_report(
    reporter: Reporter,
    report,
    *,
    workflow_url: Optional[str],
    include_raw_output: bool,
    junit_output: Optional[str],
    output_format: Optional[str],
) -> None:
    markdown = reporter.generate_markdown(
        report,
        workflow_url=workflow_url,
        include_raw_output=include_raw_output,
    )

    print(markdown)
    _write_junit_output(reporter, report, junit_output)
    _emit_machine_readable_output(
        report, output_format, include_raw_output=include_raw_output
    )

    if report.failed_count > 0:
        raise typer.Exit(code=1)


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
    working_dir: str = typer.Option(
        ...,
        "--working-dir",
        "-w",
        help="Path to an Insomnia export, legacy Git Sync repository root, or app-data directory",
    ),
    identifier: Optional[str] = typer.Option(
        None, "--identifier", "-i", help="Collection name or workspace ID"
    ),
    environment: Optional[str] = typer.Option(
        None, "--env", "-e", help="Environment name to use"
    ),
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
    request_timeout: Optional[int] = typer.Option(
        None, "--request-timeout", min=0, help="Request timeout (ms)"
    ),
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
    bail: bool = typer.Option(False, "--bail", "-b", help="Stop on first failure"),
    disable_cert_validation: bool = typer.Option(
        False, "--disable-cert-validation", "-k", help="Disable SSL verification"
    ),
    https_proxy: Optional[str] = typer.Option(
        None, "--https-proxy", help="HTTPS proxy URL"
    ),
    http_proxy: Optional[str] = typer.Option(
        None, "--http-proxy", help="HTTP proxy URL"
    ),
    no_proxy: Optional[str] = typer.Option(
        None, "--no-proxy", help="Hosts to bypass proxy"
    ),
    data_folders: Optional[list[str]] = typer.Option(
        None, "--data-folders", "-f", help="Folders Insomnia can access (repeatable)"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show additional logs"),
    execution_timeout: int = typer.Option(
        300,
        "--execution-timeout",
        min=1,
        help="Execution timeout for the entire process (seconds)",
    ),
    workflow_url: Optional[str] = typer.Option(
        None, "--workflow-url", help="GitHub workflow URL for report links"
    ),
    output_format: Optional[str] = typer.Option(
        None,
        "--output-format",
        help="The format to use for the report output (e.g., 'json').",
    ),
    include_raw_output: bool = typer.Option(
        False,
        "--include-raw-output",
        help="Include raw Inso output in Markdown and JSON reports.",
    ),
    junit_output: Optional[str] = typer.Option(
        None,
        "--junit-output",
        help="Write a JUnit XML report to this path.",
    ),
):
    """Run Insomnia collections and generate a markdown report."""

    _validate_output_format(output_format)

    if env_var:
        for pair in env_var:
            if "=" not in pair:
                raise typer.BadParameter("Invalid env-var format. Expected KEY=VALUE.")

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
    )

    runner = InsoRunner()
    try:
        report = runner.run_collection(options)
    except OSError as error:
        typer.echo(
            "Unable to execute Inso CLI. Check installation and executable permissions.",
            err=True,
        )
        raise typer.Exit(code=2) from error

    reporter = Reporter()
    _finalize_report(
        reporter,
        report,
        workflow_url=workflow_url,
        include_raw_output=include_raw_output,
        junit_output=junit_output,
        output_format=output_format,
    )


@app.command()
def run_test(  # NOSONAR - CLI command requires many options
    working_dir: str = typer.Option(
        ...,
        "--working-dir",
        "-w",
        help="Path to an Insomnia export, legacy Git Sync repository root, or app-data directory",
    ),
    identifier: Optional[str] = typer.Option(
        None, "--identifier", "-i", help="Test suite or API spec ID"
    ),
    environment: Optional[str] = typer.Option(
        None, "--env", "-e", help="Environment name to use"
    ),
    test_name_pattern: Optional[str] = typer.Option(
        None,
        "--test-name-pattern",
        "-t",
        help="Literal substring to filter test titles (Inso 13.3.1)",
    ),
    bail: bool = typer.Option(False, "--bail", "-b", help="Stop on first failure"),
    keep_file: bool = typer.Option(
        False, "--keep-file", help="Keep generated test file"
    ),
    request_timeout: Optional[int] = typer.Option(
        None, "--request-timeout", min=0, help="Request timeout (ms)"
    ),
    disable_cert_validation: bool = typer.Option(
        False, "--disable-cert-validation", "-k", help="Disable SSL verification"
    ),
    https_proxy: Optional[str] = typer.Option(
        None, "--https-proxy", help="HTTPS proxy URL"
    ),
    http_proxy: Optional[str] = typer.Option(
        None, "--http-proxy", help="HTTP proxy URL"
    ),
    no_proxy: Optional[str] = typer.Option(
        None, "--no-proxy", help="Hosts to bypass proxy"
    ),
    data_folders: Optional[list[str]] = typer.Option(
        None, "--data-folders", "-f", help="Folders Insomnia can access"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show additional logs"),
    execution_timeout: int = typer.Option(
        300,
        "--execution-timeout",
        min=1,
        help="Execution timeout for the entire process (seconds)",
    ),
    workflow_url: Optional[str] = typer.Option(
        None, "--workflow-url", help="GitHub workflow URL for report links"
    ),
    output_format: Optional[str] = typer.Option(
        None,
        "--output-format",
        help="The format to use for the report output (e.g., 'json').",
    ),
    include_raw_output: bool = typer.Option(
        False,
        "--include-raw-output",
        help="Include raw Inso output in Markdown and JSON reports.",
    ),
    junit_output: Optional[str] = typer.Option(
        None,
        "--junit-output",
        help="Write a JUnit XML report to this path.",
    ),
):
    """Run Insomnia unit tests and generate a markdown report."""

    _validate_output_format(output_format)

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

    runner = InsoRunner()
    try:
        report = runner.run_test(options)
    except OSError as error:
        typer.echo(
            "Unable to execute Inso CLI. Check installation and executable permissions.",
            err=True,
        )
        raise typer.Exit(code=2) from error

    reporter = Reporter()
    _finalize_report(
        reporter,
        report,
        workflow_url=workflow_url,
        include_raw_output=include_raw_output,
        junit_output=junit_output,
        output_format=output_format,
    )


def main():
    app()


if __name__ == "__main__":
    main()
