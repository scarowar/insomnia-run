import importlib.metadata
import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import typer

from .models import InsoCollectionOptions, InsoRunReport, InsoTestOptions
from .reporter import DEFAULT_RAW_OUTPUT_MAX_BYTES, Reporter
from .runner import InsoRunner

_SUPPORTED_OUTPUT_FORMATS = ("json",)

_OptionsT = TypeVar("_OptionsT", InsoCollectionOptions, InsoTestOptions)

app = typer.Typer(name="insomnia-run", help="CLI runner for Insomnia API tests and collections.")


def _get_version() -> str:
    try:
        return importlib.metadata.version("insomnia-run")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _validate_output_format(output_format: str | None) -> None:
    """Reject unsupported formats before any tests run."""
    if output_format and output_format.lower() not in _SUPPORTED_OUTPUT_FORMATS:
        raise typer.BadParameter(
            f"Unsupported output format: '{output_format}'. "
            f"Currently supported: {', '.join(_SUPPORTED_OUTPUT_FORMATS)}"
        )


def _emit_annotations(report: InsoRunReport) -> None:
    """Emit per-failure GitHub annotations when running inside Actions."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    for line in Reporter().annotations(report):
        typer.echo(line, err=True)


def _validate_output_path(path_str: str, label: str) -> Path:
    """Ensure output path is inside GITHUB_WORKSPACE or RUNNER_TEMP when in Actions."""
    p = Path(path_str).resolve()
    if os.environ.get("GITHUB_ACTIONS") == "true":
        workspace = os.environ.get("GITHUB_WORKSPACE", "")
        runner_temp = os.environ.get("RUNNER_TEMP", "")
        allowed_roots = [Path(r).resolve() for r in (workspace, runner_temp) if r]
        if allowed_roots and not any(p == r or p.is_relative_to(r) for r in allowed_roots):
            raise typer.BadParameter(
                f"{label} path '{path_str}' must be inside GITHUB_WORKSPACE or RUNNER_TEMP"
            )
        if not allowed_roots:
            raise typer.BadParameter(
                f"The action cannot validate the {label} path '{path_str}'. Set GITHUB_WORKSPACE or RUNNER_TEMP. Or run outside GitHub Actions."
            )
    return p


def _write_text_file(path_str: str, content: str, label: str) -> None:
    try:
        path = _validate_output_path(path_str, label)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    except OSError as exc:
        raise typer.BadParameter(f"Cannot write {label} to '{path_str}': {exc}") from exc


def _write_raw_output_file(report: InsoRunReport, raw_output_file: str) -> None:
    if not report.raw_output:
        return
    _write_text_file(raw_output_file, report.raw_output, "raw output")


def _write_junit_output(report: InsoRunReport, junit_output: str) -> None:
    _write_text_file(junit_output, Reporter().generate_junit(report), "JUnit output")


def _execute(
    options: _OptionsT,
    run: Callable[[_OptionsT], InsoRunReport],
    *,
    workflow_url: str | None = None,
    output_format: str | None = None,
    junit_output: str | None = None,
    include_raw_output: bool = True,
    raw_output_max_bytes: int = DEFAULT_RAW_OUTPUT_MAX_BYTES,
    raw_output_file: str | None = None,
) -> None:
    """Shared command tail: run, render, print, write artifacts, exit."""
    _validate_output_format(output_format)
    if junit_output:
        _validate_output_path(junit_output, "JUnit output")
    if raw_output_file:
        _validate_output_path(raw_output_file, "raw output")
    if raw_output_max_bytes <= 0:
        raise typer.BadParameter("raw-output-max-bytes must be > 0")

    report = run(options)

    markdown = Reporter().generate_markdown(
        report,
        workflow_url=workflow_url,
        include_raw_output=include_raw_output,
        raw_output_max_bytes=raw_output_max_bytes,
    )
    print(markdown)
    _emit_annotations(report)

    if junit_output:
        _write_junit_output(report, junit_output)
    if raw_output_file:
        _write_raw_output_file(report, raw_output_file)

    _emit_machine_readable_output(report, output_format)

    if report.failed_count > 0:
        raise typer.Exit(code=1)


def _emit_machine_readable_output(report: InsoRunReport, output_format: str | None) -> None:
    """Emit the report in the requested machine-readable format to stderr.

    Format validity is enforced earlier by _validate_output_format, before
    any tests run.
    """
    if not output_format:
        return

    requested_format = output_format.lower()

    if requested_format == "json":
        json_report = report.model_dump_json(indent=2)
        typer.echo(json_report, err=True)


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
    identifier: str | None = typer.Option(
        None, "--identifier", "-i", help="Collection name or workspace ID"
    ),
    environment: str | None = typer.Option(None, "--env", "-e", help="Environment name to use"),
    request_name_pattern: str | None = typer.Option(
        None, "--request-name-pattern", help="Regex to filter requests"
    ),
    item: list[str] | None = typer.Option(
        None, "--item", help="Request or folder IDs to run (repeatable)"
    ),
    globals: str | None = typer.Option(
        None, "--globals", "-g", help="Global environment file or ID"
    ),
    delay_request: int | None = typer.Option(
        None, "--delay-request", help="Delay between requests (ms)"
    ),
    request_timeout: int | None = typer.Option(
        None, "--request-timeout", help="Request timeout (ms)"
    ),
    iteration_count: int | None = typer.Option(
        None, "--iteration-count", "-n", help="Number of iterations"
    ),
    iteration_data: str | None = typer.Option(
        None, "--iteration-data", "-d", help="Path to CSV/JSON data file"
    ),
    env_var: list[str] | None = typer.Option(
        None, "--env-var", help="Override env vars (KEY=VALUE, repeatable)"
    ),
    bail: bool = typer.Option(False, "--bail", "-b", help="Stop on first failure"),
    disable_cert_validation: bool = typer.Option(
        False, "--disable-cert-validation", "-k", help="Disable SSL verification"
    ),
    https_proxy: str | None = typer.Option(None, "--https-proxy", help="HTTPS proxy URL"),
    http_proxy: str | None = typer.Option(None, "--http-proxy", help="HTTP proxy URL"),
    no_proxy: str | None = typer.Option(None, "--no-proxy", help="Hosts to bypass proxy"),
    data_folders: list[str] | None = typer.Option(
        None, "--data-folders", "-f", help="Folders Insomnia can access (repeatable)"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show additional logs"),
    execution_timeout: int = typer.Option(
        300,
        "--execution-timeout",
        help="Execution timeout for the entire process (seconds)",
    ),
    workflow_url: str | None = typer.Option(
        None, "--workflow-url", help="GitHub workflow URL for report links"
    ),
    output_format: str | None = typer.Option(
        None,
        "--output-format",
        help="The format to use for the report output (e.g., 'json').",
    ),
    junit_output: str | None = typer.Option(
        None,
        "--junit-output",
        help="Path to write a JUnit XML report (enabled when set).",
    ),
    include_raw_output: bool = typer.Option(
        True,
        "--include-raw-output / --no-include-raw-output",
        help="Embed raw Inso output in the markdown report.",
    ),
    raw_output_max_bytes: int = typer.Option(
        DEFAULT_RAW_OUTPUT_MAX_BYTES,
        "--raw-output-max-bytes",
        help="Maximum raw output size embedded in the markdown report.",
    ),
    raw_output_file: str | None = typer.Option(
        None,
        "--raw-output-file",
        help="Path to write the full (redacted) raw output (enabled when set).",
    ),
):
    """Run Insomnia collections and generate a markdown report."""

    env_var_dict = None
    if env_var:
        env_var_dict = {}
        for pair in env_var:
            if "=" not in pair:
                raise typer.BadParameter(
                    f"Invalid env-var format: '{pair}'. Expected KEY=VALUE "
                    "(e.g. --env-var API_KEY=secret)."
                )
            key, value = pair.split("=", 1)
            if 0 < len(value) < 4:
                typer.echo(
                    f"::warning::env-var '{key}' value is shorter than 4 characters "
                    "and will not be redacted from reports.",
                    err=True,
                )
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

    _execute(
        options,
        InsoRunner().run_collection,
        workflow_url=workflow_url,
        output_format=output_format,
        junit_output=junit_output,
        include_raw_output=include_raw_output,
        raw_output_max_bytes=raw_output_max_bytes,
        raw_output_file=raw_output_file,
    )


@app.command()
def run_test(  # NOSONAR - CLI command requires many options
    working_dir: str = typer.Option(
        ...,
        "--working-dir",
        "-w",
        help="Path to Insomnia export or .insomnia directory",
    ),
    identifier: str | None = typer.Option(
        None, "--identifier", "-i", help="Test suite or API spec ID"
    ),
    environment: str | None = typer.Option(None, "--env", "-e", help="Environment name to use"),
    test_name_pattern: str | None = typer.Option(
        None, "--test-name-pattern", "-t", help="Regex to filter test names"
    ),
    bail: bool = typer.Option(False, "--bail", "-b", help="Stop on first failure"),
    keep_file: bool = typer.Option(False, "--keep-file", help="Keep generated test file"),
    request_timeout: int | None = typer.Option(
        None, "--request-timeout", help="Request timeout (ms)"
    ),
    disable_cert_validation: bool = typer.Option(
        False, "--disable-cert-validation", "-k", help="Disable SSL verification"
    ),
    https_proxy: str | None = typer.Option(None, "--https-proxy", help="HTTPS proxy URL"),
    http_proxy: str | None = typer.Option(None, "--http-proxy", help="HTTP proxy URL"),
    no_proxy: str | None = typer.Option(None, "--no-proxy", help="Hosts to bypass proxy"),
    data_folders: list[str] | None = typer.Option(
        None, "--data-folders", "-f", help="Folders Insomnia can access"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Show additional logs"),
    execution_timeout: int = typer.Option(
        300,
        "--execution-timeout",
        help="Execution timeout for the entire process (seconds)",
    ),
    workflow_url: str | None = typer.Option(
        None, "--workflow-url", help="GitHub workflow URL for report links"
    ),
    output_format: str | None = typer.Option(
        None,
        "--output-format",
        help="The format to use for the report output (e.g., 'json').",
    ),
    junit_output: str | None = typer.Option(
        None,
        "--junit-output",
        help="Path to write a JUnit XML report (enabled when set).",
    ),
    include_raw_output: bool = typer.Option(
        True,
        "--include-raw-output / --no-include-raw-output",
        help="Embed raw Inso output in the markdown report.",
    ),
    raw_output_max_bytes: int = typer.Option(
        DEFAULT_RAW_OUTPUT_MAX_BYTES,
        "--raw-output-max-bytes",
        help="Maximum raw output size embedded in the markdown report.",
    ),
    raw_output_file: str | None = typer.Option(
        None,
        "--raw-output-file",
        help="Path to write the full (redacted) raw output (enabled when set).",
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

    _execute(
        options,
        InsoRunner().run_test,
        workflow_url=workflow_url,
        output_format=output_format,
        junit_output=junit_output,
        include_raw_output=include_raw_output,
        raw_output_max_bytes=raw_output_max_bytes,
        raw_output_file=raw_output_file,
    )


def main():
    app()


if __name__ == "__main__":
    main()
