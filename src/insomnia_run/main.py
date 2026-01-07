import typer
from importlib import metadata
from typing import Optional

from .models import InsoCollectionOptions, InsoTestOptions
from .runner import InsoRunner
from .reporter import Reporter

def version_callback(value: bool):
    if value:
        try:
            version = metadata.version("insomnia-run")
            typer.echo(f"insomnia-run v{version}")
        except metadata.PackageNotFoundError:
            typer.echo("insomnia-run (version unknown)")
        raise typer.Exit()

app = typer.Typer(
    name="insomnia-run",
    help="CLI runner for Insomnia API tests and collections.",
    no_args_is_help=True,
)

@app.callback(
    epilog="Use --version to show version information.",
    no_args_is_help=True,
)
def callback(
    version: bool = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version information",
    ),
):
    """
    CLI runner for Insomnia API tests and collections.
    """
    pass


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

    if report.failed_count > 0:
        raise typer.Exit(code=1)


def main():
    """CLI runner for Insomnia API tests and collections."""
    app()


if __name__ == "__main__":
    main()
