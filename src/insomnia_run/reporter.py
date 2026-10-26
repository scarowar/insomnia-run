import re
from dataclasses import dataclass, field
from decimal import Decimal
from html import escape
from urllib.parse import urlsplit

# XML is generated, not parsed.
from xml.etree import ElementTree  # nosec B405

from .models import InsoResult, InsoRunReport, InsoStatus, RequestExecution, RunType


_MAX_NAME_BYTES = 160
_MAX_RAW_OUTPUT_BYTES = 8192
_MAX_MESSAGE_BYTES = 2048
_MAX_MARKDOWN_BYTES = 60000
_DETAILS_CLOSE = "\n</details>\n\n"


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
        marker = " ... (truncated)"
        if budget < len(marker):
            return marker[: max(0, budget)]
        return encoded[: budget - len(marker)].decode("utf-8", errors="ignore") + marker
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


def _display_message(value: str) -> str:
    text = re.sub(r"^error:\s+(?:(?:Assertion)?Error:\s+)?", "", value, count=1)
    trailer = "| ACTUAL: undefined | EXPECTED: undefined"
    if text.endswith(trailer):
        text = text[: -len(trailer)].rstrip()
    if "\n" in text:
        text = re.sub(
            r" \| ACTUAL: ([^\r\n|]{0,512}) \| EXPECTED: ([^\r\n|]{0,512})$",
            r"\nActual: \1 | Expected: \2",
            text,
        )
    return text


def _literal_block(value: str, max_bytes: int | None = None) -> str:
    text = _bounded_text(value, _MAX_MESSAGE_BYTES)
    opening, closing = "<pre><code>", "</code></pre>\n\n"
    block = opening + escape(text, quote=False) + closing
    if max_bytes is None or len(block.encode("utf-8")) <= max_bytes:
        return block
    marker = " ... (truncated)"
    available = max_bytes - len((opening + closing + marker).encode("utf-8"))
    if available < 1:
        return ""
    pieces = []
    for char in text:
        escaped = escape(char, quote=False)
        size = len(escaped.encode("utf-8"))
        if size > available:
            break
        pieces.append(escaped)
        available -= size
    return opening + "".join(pieces) + marker + closing


def _duration(value: float) -> str:
    return "<1 ms" if 0 < value < 0.001 else f"{value:.3f} s"


def _result_block(
    result: InsoResult, *, include_message: bool = True, native: bool = False
) -> str:
    icon = {InsoStatus.PASS: "✅", InsoStatus.FAIL: "❌", InsoStatus.SKIP: "⏭️"}[
        result.status
    ]
    timing = (
        f" ({escape(_duration(result.duration_seconds))})"
        if result.duration_seconds is not None
        else ""
    )
    block = f"- {icon} **{_inline_code(result.description)}**{timing}\n"
    if include_message and result.message:
        block += "\n" + _literal_block(
            _display_message(result.message) if native else result.message
        )
    return block


@dataclass(frozen=True)
class _RequestFrame:
    opening: str
    closing: str
    passing_open: str = ""
    passing_close: str = ""


@dataclass
class _MarkdownGroup:
    execution: RequestExecution | None
    results: list[InsoResult]
    frame: _RequestFrame
    selected: dict[int, str] = field(default_factory=dict)
    reasons: dict[int, str] = field(default_factory=dict)
    headers: str = ""


def _request_metadata(execution: RequestExecution, summary: str) -> str:
    metadata = [summary, f"Execution {execution.id}"]
    if execution.iteration is not None:
        metadata.append(f"Iteration {execution.iteration + 1}")
    if execution.status_code is not None:
        status = (
            " " + _bounded_text(" ".join(execution.status.split()), _MAX_NAME_BYTES)
            if execution.status
            else ""
        )
        metadata.append(escape(f"HTTP {execution.status_code}{status}"))
    elif execution.status:
        metadata.append(
            "Status: "
            + escape(_bounded_text(" ".join(execution.status.split()), _MAX_NAME_BYTES))
        )
    if execution.duration_seconds is not None:
        metadata.append(escape(_duration(execution.duration_seconds)))
    return " | ".join(metadata)


def _request_frame(
    execution: RequestExecution | None, results: list[InsoResult]
) -> _RequestFrame:
    counts = {
        status: sum(result.status == status for result in results)
        for status in InsoStatus
    }
    summary = (
        ", ".join(
            f"{counts[status]} {label}"
            for status, label in (
                (InsoStatus.FAIL, "failed"),
                (InsoStatus.PASS, "passed"),
                (InsoStatus.SKIP, "skipped"),
            )
            if counts[status]
        )
        or "0 assertions"
    )
    if execution is None:
        opening, closing = f"#### Unattributed assertions ({summary})\n\n", "\n"
    else:
        details = _request_metadata(execution, summary)
        if counts[InsoStatus.FAIL]:
            opening, closing = (
                f"#### ❌ Request: {_inline_code(execution.name)}\n\n{details}\n\n",
                "\n",
            )
        else:
            name = escape(
                _bounded_text(" ".join(execution.name.split()), _MAX_NAME_BYTES)
            )
            empty = "No assertions recorded.\n\n" if not results else ""
            opening, closing = (
                f"<details><summary><code>{name}</code> | {details}</summary>\n\n{empty}",
                _DETAILS_CLOSE,
            )
    collapse = counts[InsoStatus.PASS] and counts[InsoStatus.FAIL]
    return _RequestFrame(
        opening,
        closing,
        f"<details><summary>{counts[InsoStatus.PASS]} passed assertions</summary>\n\n"
        if collapse
        else "",
        _DETAILS_CLOSE if collapse else "",
    )


def _response_headers(
    execution: RequestExecution | None, max_bytes: int | None = None
) -> str:
    if execution is None or not execution.headers:
        return ""
    label = "**Response headers:**\n\n"
    text = "\n".join(f"{name}: {value}" for name, value in execution.headers.items())
    body = _literal_block(
        text,
        max_bytes=max_bytes - len(label.encode("utf-8"))
        if max_bytes is not None
        else None,
    )
    return label + body if body else ""


def _group_omission(
    results: list[InsoResult], shown: list[InsoResult], reasons: int
) -> str:
    parts = []
    for status in InsoStatus:
        missing = sum(result.status == status for result in results) - sum(
            result.status == status for result in shown
        )
        if missing:
            parts.append(
                f"{missing} {status.value.lower()} assertions omitted in this request"
            )
    missing_reasons = sum(bool(result.message) for result in shown) - reasons
    if missing_reasons:
        parts.append(f"{missing_reasons} assertion reasons omitted in this request")
    return "".join(
        f"- {part}; full details remain in JSON and JUnit reports.\n\n"
        for part in parts
    )


def _global_omission(results: int, failures: int, groups: int) -> str:
    return (
        (
            f"- {results} more results omitted; full details remain in JSON and JUnit reports.\n\n"
            if results
            else ""
        )
        + (f"- {failures} failures omitted.\n\n" if failures else "")
        + (
            f"- {groups} request groups omitted; full details remain in JSON reports.\n\n"
            if groups
            else ""
        )
    )


def _complete_groups(
    groups: list[_MarkdownGroup], budget: int, *, native: bool
) -> str | None:
    # Avoid reserving omission notices when the complete report already fits.
    blocks = []
    for group in groups:
        frame = group.frame
        passing_open = frame.passing_open
        pieces = [frame.opening]
        size = len(
            (frame.opening + frame.closing + passing_open + frame.passing_close).encode(
                "utf-8"
            )
        )
        for result in sorted(
            group.results,
            key=lambda result: (
                result.status != InsoStatus.FAIL,
                result.status == InsoStatus.PASS,
            ),
        ):
            block = _result_block(result, native=native)
            size += len(block.encode("utf-8"))
            if size > budget:
                return None
            if passing_open and result.status == InsoStatus.PASS:
                pieces.append(passing_open)
                passing_open = ""
            pieces.append(block)
        headers = _response_headers(group.execution)
        size += len(headers.encode("utf-8"))
        if size > budget:
            return None
        pieces.extend((frame.passing_close, headers, frame.closing))
        budget -= size
        blocks.append("".join(pieces))
    return "".join(blocks)


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


def _select_reasons(group: _MarkdownGroup, budget: int, *, native: bool) -> int:
    for ordinal in group.selected:
        message = group.results[ordinal].message
        if message and ordinal not in group.reasons:
            block = _literal_block(
                _display_message(message) if native else message, max_bytes=budget - 1
            )
            if block:
                group.reasons[ordinal] = "\n" + block
                budget -= len(group.reasons[ordinal].encode("utf-8"))
    return budget


def _visible_groups(
    groups: list[_MarkdownGroup], budget: int
) -> tuple[list[_MarkdownGroup], int]:
    visible = []
    for group in groups:
        frame = group.frame
        reserve = _group_omission(group.results, [], 0) + _group_omission(
            group.results, group.results, 0
        )
        size = len(
            (
                frame.opening
                + frame.closing
                + reserve
                + frame.passing_open
                + frame.passing_close
            ).encode("utf-8")
        )
        if size <= budget:
            budget -= size
            visible.append(group)
    return visible, budget


def _select_descriptions(group: _MarkdownGroup, status: InsoStatus, budget: int) -> int:
    for ordinal, result in enumerate(group.results):
        if result.status != status:
            continue
        block = _result_block(result, include_message=False)
        size = len(block.encode("utf-8"))
        if size <= budget:
            group.selected[ordinal] = block
            budget -= size
    return budget


def _select_results(
    visible: list[_MarkdownGroup], budget: int, *, native: bool
) -> None:
    for status in (InsoStatus.FAIL, InsoStatus.SKIP, InsoStatus.PASS):
        for group in visible:
            budget = _select_descriptions(group, status, budget)
        if status == InsoStatus.FAIL:
            for group in visible:
                budget = _select_reasons(group, budget, native=native)
    for group in visible:
        budget = _select_reasons(group, budget, native=native)
        group.headers = _response_headers(group.execution, max_bytes=budget)
        budget -= len(group.headers.encode("utf-8"))


def _render_selected(visible: list[_MarkdownGroup], report: InsoRunReport) -> str:
    blocks = []
    shown_results = shown_failures = shown_executions = 0
    for group in visible:
        shown = [group.results[ordinal] for ordinal in group.selected]
        nonpassing: list[str] = []
        passing: list[str] = []
        for ordinal in sorted(
            group.selected,
            key=lambda n: (
                group.results[n].status != InsoStatus.FAIL,
                group.results[n].status == InsoStatus.PASS,
                n,
            ),
        ):
            block = group.selected[ordinal] + group.reasons.get(ordinal, "")
            (
                passing
                if group.results[ordinal].status == InsoStatus.PASS
                else nonpassing
            ).append(block)
        body = "".join(nonpassing)
        if passing:
            body += (
                group.frame.passing_open + "".join(passing) + group.frame.passing_close
            )
        body += _group_omission(group.results, shown, len(group.reasons))
        blocks.append(group.frame.opening + body + group.headers + group.frame.closing)
        shown_results += len(shown)
        shown_failures += sum(result.status == InsoStatus.FAIL for result in shown)
        shown_executions += int(group.execution is not None)
    blocks.append(
        _global_omission(
            report.total_tests - shown_results,
            report.failed_count - shown_failures,
            len(report.executions) - shown_executions,
        )
    )
    return "".join(blocks)


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


def _junit_summary(message: str) -> str:
    return _bounded_text(message.splitlines()[0] if message.splitlines() else "", 512)


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
            testcase, "failure", {"message": _junit_summary(message or description)}
        )
        failure.text = message or "Inso reported this test as failed."
    elif result.status == InsoStatus.SKIP:
        skipped = ElementTree.SubElement(
            testcase, "skipped", {"message": _junit_summary(message)} if message else {}
        )
        skipped.text = message


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
        if (
            report.run_type == RunType.COLLECTION
            and report.source == "tap"
            and report.results
        ):
            lines.append(
                "- Native report unavailable; recovered TAP may omit "
                "request details and assertion reasons."
            )
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
        *,
        max_bytes: int = _MAX_MARKDOWN_BYTES,
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
        if len((prefix + suffix).encode("utf-8")) + 512 > max_bytes:
            suffix = "### Additional Information\n\nFull details remain in JSON and JUnit reports.\n"
        if len((prefix + suffix).encode("utf-8")) + 512 > max_bytes:
            status, _ = _report_status(report)
            return _bounded_text(
                f"Insomnia {self._run_label(report)} {status}: {report.total_tests} results, {report.failed_count} failed. Details omitted; see JSON and JUnit reports.",
                max_bytes,
            )
        return (
            prefix
            + self._markdown_results(
                report, max_bytes - len((prefix + suffix).encode("utf-8"))
            )
            + suffix
        )

    @staticmethod
    def _markdown_results(report: InsoRunReport, budget: int) -> str:
        groups = [
            _MarkdownGroup(execution, results, _request_frame(execution, results))
            for execution, results in _result_groups(report)
        ]
        complete = _complete_groups(groups, budget, native=report.source == "native")
        if complete is not None:
            return complete
        budget -= len(
            _global_omission(
                report.total_tests, report.failed_count, len(report.executions)
            ).encode("utf-8")
        )
        visible, budget = _visible_groups(groups, budget)
        _select_results(visible, budget, native=report.source == "native")
        return _render_selected(visible, report)

    def generate_junit(self, report: InsoRunReport) -> str:
        run_label = self._run_label(report)
        suite_name = f"Insomnia {run_label}"
        classname = _xml_text(report.target_name or suite_name)
        run_error = report.evidence_error
        suite = ElementTree.Element(
            "testsuite",
            {
                "name": suite_name,
                "tests": str(report.total_tests + int(run_error is not None)),
                "failures": str(report.failed_count),
                "errors": str(int(run_error is not None)),
                "skipped": str(report.skipped_count),
            },
        )
        executions = {execution.id: execution for execution in report.executions}
        for result in report.results:
            execution = (
                executions.get(result.execution_id)
                if result.execution_id is not None
                else None
            )
            context = classname
            if execution is not None:
                context += f" / {execution.name} / Execution {execution.id}"
                if execution.iteration is not None:
                    context += f" / Iteration {execution.iteration + 1}"
            _junit_result(suite, _xml_text(context), result)

        if run_error:
            testcase = ElementTree.SubElement(
                suite, "testcase", {"classname": classname, "name": "Inso run error"}
            )
            message = _xml_text(run_error.message)
            error = ElementTree.SubElement(
                testcase,
                "error",
                {"type": run_error.kind, "message": _junit_summary(message)},
            )
            error.text = message
        if report.duration_seconds is not None:
            suite.set("time", _junit_time(report.duration_seconds))
        elif report.results and all(
            result.duration_seconds is not None for result in report.results
        ):
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
