import importlib.metadata
import typer
from typing import Optional

from .models import InsoCollectionOptions, InsoTestOptions
from .runner import InsoRunner
from .reporter import Reporter

app = typer.Typer(
    name="insomnia-run", help="CLI runner for Insomnia API tests and collections."
)


def _get_version() -> str:
    try:
        return importlib.metadata.version("insomnia-run")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"

def _emit_machine_readable_output(report, output_format: Optional[str]) -> None:
    """
    Emits the test report in the specified machine-readable format to stderr.

    This helper handles validation of the requested format and ensures
    consistent output behavior across different CLI commands.
    """
    if not output_format:
        return

    requested_format = output_format.lower()

    if requested_format == "json":
        json_report = report.model_dump_json(indent=2)
        typer.echo(json_report, err=True)
    else:
        raise typer.BadParameter(
            f"Unsupported output format: '{output_format}'. "
            f"Currently supported: json"
        )

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
        help="Path to Insomnia export or .insomnia directory",
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
        None, "--globals", "-g", help="Global environment file or ID"
    ),
    delay_request: Optional[int] = typer.Option(
        None, "--delay-request", help="Delay between requests (ms)"
    ),
    request_timeout: Optional[int] = typer.Option(
        None, "--request-timeout", help="Request timeout (ms)"
    ),
    iteration_count: Optional[int] = typer.Option(
        None, "--iteration-count", "-n", help="Number of iterations"
    ),
    iteration_data: Optional[str] = typer.Option(
        None, "--iteration-data", "-d", help="Path to CSV/JSON data file"
    ),
    env_var: Optional[list[str]] = typer.Option(
        None, "--env-var", help="Override env vars (KEY=VALUE, repeatable)"
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
        300, "--execution-timeout", help="Execution timeout for the entire process (seconds)"
    ),
    workflow_url: Optional[str] = typer.Option(
        None, "--workflow-url", help="GitHub workflow URL for report links"
    ),
    output_format: Optional[str] = typer.Option(
        None,
        "--output-format",
        help="The format to use for the report output (e.g., 'json')."
    ),
):
    """Run Insomnia collections and generate a markdown report."""

    env_var_dict = None
    if env_var:
        env_var_dict = {}
        for pair in env_var:
            if "=" not in pair:
                raise typer.BadParameter(
                    f"Invalid env-var format: '{pair}'. Expected KEY=VALUE."
                )
            key, value = pair.split("=", 1)
            env_var_dict[key] = value

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
        env_var=env_var_dict,
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
    report = runner.run_collection(options)

    reporter = Reporter()
    markdown = reporter.generate_markdown(report, workflow_url=workflow_url)

    print(markdown)
    _emit_machine_readable_output(report, output_format)

    if report.failed_count > 0:
        raise typer.Exit(code=1)


@app.command()
def run_test(  # NOSONAR - CLI command requires many options
    working_dir: str = typer.Option(
        ...,
        "--working-dir",
        "-w",
        help="Path to Insomnia export or .insomnia directory",
    ),
    identifier: Optional[str] = typer.Option(
        None, "--identifier", "-i", help="Test suite or API spec ID"
    ),
    environment: Optional[str] = typer.Option(
        None, "--env", "-e", help="Environment name to use"
    ),
    test_name_pattern: Optional[str] = typer.Option(
        None, "--test-name-pattern", "-t", help="Regex to filter test names"
    ),
    bail: bool = typer.Option(False, "--bail", "-b", help="Stop on first failure"),
    keep_file: bool = typer.Option(
        False, "--keep-file", help="Keep generated test file"
    ),
    request_timeout: Optional[int] = typer.Option(
        None, "--request-timeout", help="Request timeout (ms)"
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
        300, "--execution-timeout", help="Execution timeout for the entire process (seconds)"
    ),
    workflow_url: Optional[str] = typer.Option(
        None, "--workflow-url", help="GitHub workflow URL for report links"
    ),
    output_format: Optional[str] = typer.Option(
        None,
        "--output-format",
        help="The format to use for the report output (e.g., 'json')."
    ),
):
    """Run Insomnia unit tests and generate a markdown report."""

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
    report = runner.run_test(options)

    reporter = Reporter()
    markdown = reporter.generate_markdown(report, workflow_url=workflow_url)

    print(markdown)
    _emit_machine_readable_output(report, output_format)

    if report.failed_count > 0:
        raise typer.Exit(code=1)


def main():
    app()


if __name__ == "__main__":
    main()
