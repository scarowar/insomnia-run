import re
from decimal import Decimal
from html import escape
from urllib.parse import urlsplit

# XML is generated, not parsed.
from xml.etree import ElementTree  # nosec B405

from .models import InsoResult, InsoRunReport, InsoStatus, RequestExecution, RunType


_MAX_RENDERED_RESULTS = 50
_MAX_NAME_BYTES = 160
_MAX_RAW_OUTPUT_BYTES = 8192
_MAX_MESSAGE_BYTES = 2048
_MAX_MARKDOWN_BYTES = 60000


def _xml_text(value: str) -> str:
    # XML 1.0 forbids some characters that are valid in Python strings.
    return re.sub(
        r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]",
        "\ufffd",
        value,
    )


def _bounded_text(value: str, budget: int) -> str:
    text = _xml_text(value)
    encoded = text.encode("utf-8")
    if len(encoded) > budget:
        return encoded[:budget].decode("utf-8", errors="ignore") + " ... (truncated)"
    return text


def _inline_code(value: str) -> str:
    text = _bounded_text(" ".join(value.split()), _MAX_NAME_BYTES)
    # GFM limits delimiter runs; the shortest unused run stays small for bounded names.
    used_lengths = {len(match[0]) for match in re.finditer(r"`+", text)}
    length = 1
    while length in used_lengths:
        length += 1
    delimiter = "`" * length
    return f"{delimiter} {text} {delimiter}"


def _workflow_link(workflow_url: str | None) -> str:
    fallback = "workflow run"
    if (
        not workflow_url
        or re.search(r"[<>\\\x00-\x1f\x7f\uD800-\uDFFF]", workflow_url)
        or len(workflow_url.encode("utf-8")) > 2048
        or any(char.isspace() for char in workflow_url)
    ):
        return fallback
    try:
        url = urlsplit(workflow_url)
        if url.scheme in {"http", "https"} and url.hostname:
            return f"[workflow run](<{workflow_url}>)"
    except ValueError:
        return fallback
    return fallback


def _literal_block(value: str) -> str:
    text = escape(_bounded_text(value, _MAX_MESSAGE_BYTES), quote=False)
    return f"<pre><code>{text}</code></pre>\n\n"


def _result_block(result: InsoResult) -> str:
    icon = {InsoStatus.PASS: "✅", InsoStatus.FAIL: "❌", InsoStatus.SKIP: "⏭️"}[
        result.status
    ]
    timing = (
        f" ({result.duration_seconds:.3f} s)"
        if result.duration_seconds is not None
        else ""
    )
    block = f"- {icon} **{_inline_code(result.description)}**{timing}\n"
    if result.message:
        # Inso's ACTUAL/EXPECTED markers can occur inside values; keep the literal reason.
        block += "\n" + _literal_block(result.message)
    return block


def _request_frame(
    execution: RequestExecution, results: list[InsoResult]
) -> tuple[str, str]:
    metadata = [f"Execution {execution.id}"]
    if execution.iteration is not None:
        metadata.append(f"Iteration {execution.iteration + 1}")
    if execution.status_code is not None:
        metadata.append(f"HTTP {execution.status_code}")
    if execution.duration_seconds is not None:
        metadata.append(f"{execution.duration_seconds:.3f} s")
    details = " | ".join(metadata)
    if any(result.status == InsoStatus.FAIL for result in results):
        opening = f"#### ❌ Request: {_inline_code(execution.name)}\n\n{details}\n\n"
        closing = ""
    else:
        name = escape(_bounded_text(" ".join(execution.name.split()), _MAX_NAME_BYTES))
        opening = f"<details><summary><code>{name}</code> | {details}</summary>\n\n"
        closing = "</details>\n\n"
    if execution.status:
        opening += f"Status: {_inline_code(execution.status)}\n\n"
    if execution.headers:
        opening += _literal_block(
            "\n".join(f"{name}: {value}" for name, value in execution.headers.items())
        )
    if not results:
        opening += "No assertions recorded.\n\n"
    return opening, closing


def _result_groups(
    report: InsoRunReport,
) -> list[tuple[RequestExecution | None, list[InsoResult]]]:
    grouped: dict[int, list[InsoResult]] = {
        execution.id: [] for execution in report.executions
    }
    unattributed = []
    for result in report.results:
        matches = (
            grouped.get(result.execution_id)
            if result.execution_id is not None
            else None
        )
        if matches is not None:
            matches.append(result)
        else:
            unattributed.append(result)
    groups: list[tuple[RequestExecution | None, list[InsoResult]]] = [
        (execution, grouped[execution.id]) for execution in report.executions
    ]
    if unattributed:
        groups.append((None, unattributed))
    return sorted(
        groups, key=lambda group: not any(r.status == InsoStatus.FAIL for r in group[1])
    )


def _select_result_blocks(
    results: list[InsoResult], limit: int, budget: int
) -> list[str]:
    blocks = []
    prioritized = sorted(results, key=lambda result: result.status != InsoStatus.FAIL)
    for result in prioritized[:limit]:
        block = _result_block(result)
        size = len(block.encode("utf-8"))
        if size > budget:
            break
        blocks.append(block)
        budget -= size
    return blocks


def _junit_time(value: float | Decimal) -> str:
    return format(Decimal(str(value)).normalize(), "f")


def _report_status(report: InsoRunReport) -> tuple[str, str]:
    if report.run_error or report.failed_count:
        return "Failed", "❌"
    if not report.complete:
        return "Incomplete", "⏭️"
    if not report.total_tests:
        return "No Assertions Executed", "⏭️"
    if report.skipped_count == report.total_tests:
        return "Skipped", "⏭️"
    return "Passed", "✅"


def _junit_result(
    suite: ElementTree.Element, classname: str, result: InsoResult
) -> None:
    description = _xml_text(result.description)
    attributes = {"classname": classname, "name": description}
    if result.duration_seconds is not None:
        attributes["time"] = _junit_time(result.duration_seconds)
    testcase = ElementTree.SubElement(suite, "testcase", attributes)
    message = _xml_text(result.message) if result.message else None
    if result.status == InsoStatus.FAIL:
        failure = ElementTree.SubElement(
            testcase, "failure", {"message": message or description}
        )
        failure.text = message or "Inso reported this test as failed."
    elif result.status == InsoStatus.SKIP:
        ElementTree.SubElement(
            testcase, "skipped", {"message": message} if message else {}
        )


class Reporter:
    @staticmethod
    def _run_label(report: InsoRunReport) -> str:
        return "Collection" if report.run_type == RunType.COLLECTION else "Test Suite"

    def _markdown_summary(self, report: InsoRunReport) -> str:
        lines = []

        run_label = self._run_label(report)
        status, icon = _report_status(report)
        target_name = _inline_code(report.target_name) if report.target_name else ""
        target = f": {target_name}" if target_name else ""
        lines.extend(
            [
                f"## {icon} Insomnia {run_label} {status}{target}",
                "",
                "### Test Summary",
                "",
            ]
        )
        if not report.total_tests:
            passed_text = "(No assertions executed)"
        elif report.failed_count == 0 and report.skipped_count == 0:
            passed_text = "(all passed)"
        elif report.skipped_count > 0:
            passed_text = f"({report.passed_count} passed, {report.failed_count} failed, {report.skipped_count} skipped)"
        else:
            passed_text = (
                f"({report.passed_count} passed, {report.failed_count} failed)"
            )
        result_label = "test result" if report.total_tests == 1 else "test results"
        lines.append(f"- **{report.total_tests} {result_label}** {passed_text}")
        if report.target_name:
            lines.append(f"- **Target:** {target_name}")
        if report.request_count is not None:
            lines.append(f"- **Completed requests:** {report.request_count}")
        if not report.complete:
            lines.append("- **Evidence:** Incomplete; completed results only.")
        prefix = "\n".join(lines) + "\n\n"
        if report.run_error:
            prefix += f"### Run Error\n\n{report.run_error.kind}\n\n"
            prefix += _literal_block(report.run_error.message)
        return prefix + "### Test Results\n\n"

    def generate_markdown(
        self,
        report: InsoRunReport,
        workflow_url: str | None = None,
        include_raw_output: bool = False,
    ) -> str:
        prefix = self._markdown_summary(report)
        lines = ["### Additional Information", ""]
        lines.append(f"See the {_workflow_link(workflow_url)} for execution details.")
        if not include_raw_output:
            lines.append(
                "Raw Inso diagnostics are omitted. Enable `include-raw-output` "
                "(CLI: `--include-raw-output`) only when safe: diagnostics can "
                "contain secrets."
            )
        lines.append("")

        if include_raw_output and report.raw_output:
            encoded = _xml_text(report.raw_output.strip()).encode("utf-8")
            raw_output = encoded[:_MAX_RAW_OUTPUT_BYTES].decode(
                "utf-8", errors="ignore"
            )
            lines.extend(
                [
                    "<details><summary>View raw output</summary>",
                    "",
                    f"<pre><code>{escape(raw_output, quote=False)}</code></pre>",
                ]
            )
            if len(encoded) > _MAX_RAW_OUTPUT_BYTES:
                lines.extend(
                    ["", f"Raw output truncated at {_MAX_RAW_OUTPUT_BYTES} bytes."]
                )
            lines.append("</details>")

        suffix = "\n".join(lines)
        return prefix + self._markdown_results(report, prefix, suffix) + suffix

    @staticmethod
    def _markdown_results(report: InsoRunReport, prefix: str, suffix: str) -> str:
        omission = (
            f"- {report.total_tests} more results omitted; full details remain in JSON and JUnit reports.\n\n"
            f"- {len(report.executions)} request groups omitted; full details remain in JSON reports.\n\n"
        )
        available = _MAX_MARKDOWN_BYTES - len(
            (prefix + suffix + omission).encode("utf-8")
        )
        blocks = []
        shown_results = 0
        shown_executions = 0
        for execution, results in _result_groups(report):
            if results and shown_results == _MAX_RENDERED_RESULTS:
                continue
            opening, closing = (
                _request_frame(execution, results) if execution else ("", "")
            )
            separator = "\n" if execution else ""
            size = len((opening + separator + closing).encode("utf-8"))
            if size > available:
                continue
            selected = _select_result_blocks(
                results, _MAX_RENDERED_RESULTS - shown_results, available - size
            )
            block = opening + "".join(selected) + separator + closing
            blocks.append(block)
            available -= len(block.encode("utf-8"))
            shown_results += len(selected)
            shown_executions += int(execution is not None)
        omitted_results = report.total_tests - shown_results
        if omitted_results:
            blocks.append(
                f"- {omitted_results} more results omitted; full details remain in JSON and JUnit reports.\n\n"
            )
        omitted_executions = len(report.executions) - shown_executions
        if omitted_executions:
            blocks.append(
                f"- {omitted_executions} request groups omitted; full details remain in JSON reports.\n\n"
            )
        return "".join(blocks)

    def generate_junit(self, report: InsoRunReport) -> str:
        run_label = self._run_label(report)
        suite_name = f"Insomnia {run_label}"
        classname = _xml_text(report.target_name or suite_name)
        suite = ElementTree.Element(
            "testsuite",
            {
                "name": suite_name,
                "tests": str(report.total_tests + int(report.run_error is not None)),
                "failures": str(report.failed_count),
                "errors": str(int(report.run_error is not None)),
                "skipped": str(report.skipped_count),
            },
        )
        for result in report.results:
            _junit_result(suite, classname, result)

        if report.run_error:
            testcase = ElementTree.SubElement(
                suite, "testcase", {"classname": classname, "name": "Inso run error"}
            )
            message = _xml_text(report.run_error.message)
            error = ElementTree.SubElement(
                testcase, "error", {"type": report.run_error.kind, "message": message}
            )
            error.text = message
        elif all(result.duration_seconds is not None for result in report.results):
            duration = sum(
                (
                    Decimal(str(result.duration_seconds or 0))
                    for result in report.results
                ),
                start=Decimal(0),
            )
            suite.set(
                "time",
                _junit_time(duration),
            )

        ElementTree.indent(suite, space="  ")
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            + ElementTree.tostring(suite, encoding="unicode")
            + "\n"
        )
