"""CLI option declarations shared by the two execution commands."""

from dataclasses import dataclass
from typing import Any

import click
from typer.core import TyperCommand, TyperOption


@dataclass
class ReportOptions:
    workflow_url: str | None = None
    output_format: str | None = None
    include_raw_output: bool = False
    junit_output: str | None = None
    json_output: str | None = None
    markdown_output: str | None = None
    raw_output_file: str | None = None
    redact_value: list[str] | None = None
    progress: bool = False
    annotations: bool = False

    @property
    def destinations(self) -> dict[str, str | None]:
        return {
            "JUnit": self.junit_output,
            "JSON": self.json_output,
            "Markdown": self.markdown_output,
            "raw": self.raw_output_file,
        }


def _collect_option(ctx: click.Context, option: click.Parameter, value: Any) -> None:
    if option.multiple:
        value = list(value) or None
    ctx.meta.setdefault("run_options", {})[option.name] = value


@dataclass(frozen=True)
class _Option:
    flags: str
    help: str
    default: Any = None
    minimum: int | None = None
    multiple: bool = False
    required: bool = False

    def parameter(self, name: str, help_override: str | None) -> TyperOption:
        value_type: Any = str
        if self.minimum is not None:
            value_type = click.IntRange(min=self.minimum)
        elif isinstance(self.default, bool):
            value_type = bool
        return TyperOption(
            param_decls=[name, *self.flags.split()],
            help=help_override or self.help,
            default=self.default,
            type=value_type,
            is_flag=isinstance(self.default, bool),
            required=self.required,
            multiple=self.multiple,
            show_default=True,
            expose_value=False,
            callback=_collect_option,
        )


_OPTIONS = {
    "working_dir": _Option(
        "--working-dir -w",
        "Path to an Insomnia export, legacy Git Sync repository root, or app-data directory",
        required=True,
    ),
    "identifier": _Option("--identifier -i", "Collection name or workspace ID"),
    "environment": _Option("--env -e", "Environment name to use"),
    "request_name_pattern": _Option(
        "--request-name-pattern", "Regex to filter requests"
    ),
    "item": _Option(
        "--item", "Request or folder IDs to run (repeatable)", multiple=True
    ),
    "globals": _Option("--globals -g", "Global environment file, ID, or name"),
    "delay_request": _Option(
        "--delay-request", "Delay between requests (ms)", minimum=0
    ),
    "request_timeout": _Option("--request-timeout", "Request timeout (ms)", minimum=0),
    "iteration_count": _Option(
        "--iteration-count -n", "Number of iterations", minimum=1
    ),
    "iteration_data": _Option(
        "--iteration-data -d", "CSV/JSON iteration data path or HTTP(S) URL"
    ),
    "env_var": _Option(
        "--env-var",
        "Override env vars (KEY=VALUE, repeatable; Inso URL decoding)",
        multiple=True,
    ),
    "bail": _Option("--bail -b", "Stop on first failure", default=False),
    "disable_cert_validation": _Option(
        "--disable-cert-validation -k", "Disable SSL verification", default=False
    ),
    "https_proxy": _Option("--https-proxy", "HTTPS proxy URL"),
    "http_proxy": _Option("--http-proxy", "HTTP proxy URL"),
    "no_proxy": _Option("--no-proxy", "Hosts to bypass proxy"),
    "data_folders": _Option(
        "--data-folders -f", "Folders Insomnia can access (repeatable)", multiple=True
    ),
    "verbose": _Option("--verbose", "Show additional logs", default=False),
    "execution_timeout": _Option(
        "--execution-timeout",
        "Execution timeout for the entire process (seconds)",
        default=300,
        minimum=1,
    ),
    "workflow_url": _Option("--workflow-url", "GitHub workflow URL for report links"),
    "output_format": _Option(
        "--output-format", "The format to use for the report output (e.g., 'json')."
    ),
    "include_raw_output": _Option(
        "--include-raw-output",
        "Include raw Inso output in Markdown and JSON reports.",
        default=False,
    ),
    "junit_output": _Option("--junit-output", "Write a JUnit XML report to this path."),
    "json_output": _Option(
        "--json-output", "Write a normalized JSON report to this path."
    ),
    "markdown_output": _Option(
        "--markdown-output", "Write a Markdown report to this path."
    ),
    "raw_output_file": _Option(
        "--raw-output-file", "Write redacted raw Inso output to this path."
    ),
    "redact_value": _Option(
        "--redact-value", "Additional value to redact (repeatable).", multiple=True
    ),
    "capture_response_headers": _Option(
        "--capture-response-headers", "Comma-separated response header names to retain."
    ),
    "progress": _Option(
        "--progress",
        "Show execution stages and elapsed-time heartbeats.",
        default=False,
    ),
    "annotations": _Option(
        "--annotations", "Emit bounded GitHub failure annotations.", default=False
    ),
    "test_name_pattern": _Option(
        "--test-name-pattern -t",
        "Literal substring to filter test titles (Inso 13.3.1)",
    ),
    "keep_file": _Option("--keep-file", "Keep generated test file", default=False),
}


class _RunCommand(TyperCommand):
    option_names: tuple[str, ...] = ()
    help_overrides: dict[str, str] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.params.extend(
            _OPTIONS[name].parameter(name, self.help_overrides.get(name))
            for name in self.option_names
        )


class CollectionCommand(_RunCommand):
    option_names = (
        "working_dir",
        "identifier",
        "environment",
        "request_name_pattern",
        "item",
        "globals",
        "delay_request",
        "request_timeout",
        "iteration_count",
        "iteration_data",
        "env_var",
        "bail",
        "disable_cert_validation",
        "https_proxy",
        "http_proxy",
        "no_proxy",
        "data_folders",
        "verbose",
        "execution_timeout",
        "workflow_url",
        "output_format",
        "include_raw_output",
        "junit_output",
        "json_output",
        "markdown_output",
        "raw_output_file",
        "redact_value",
        "capture_response_headers",
        "progress",
        "annotations",
    )


class TestCommand(_RunCommand):
    option_names = (
        "working_dir",
        "identifier",
        "environment",
        "test_name_pattern",
        "bail",
        "keep_file",
        "request_timeout",
        "disable_cert_validation",
        "https_proxy",
        "http_proxy",
        "no_proxy",
        "data_folders",
        "verbose",
        "execution_timeout",
        "workflow_url",
        "output_format",
        "include_raw_output",
        "junit_output",
        "json_output",
        "markdown_output",
        "raw_output_file",
        "redact_value",
        "progress",
        "annotations",
    )
    help_overrides = {
        "identifier": "Test suite or API spec ID",
        "data_folders": "Folders Insomnia can access",
    }
