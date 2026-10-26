import re
from collections import Counter
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
_LINE_BREAK = "<br /> "
_OVERVIEW_HEADER = "| Request | Passed | Failed | Skipped | Response |\n| --- | ---: | ---: | ---: | --- |\n"
_FAILURE_HEADER = (
    "### Failed assertions\n\n| Request | Assertion | Failure |\n| --- | --- | --- |\n"
)
_OMITTED_PREVIEW = "Failure reason omitted"
_STATUS_LABELS = {
    InsoStatus.PASS: "passed",
    InsoStatus.FAIL: "failed",
    InsoStatus.SKIP: "skipped",
}


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
            r"\nActual: \1\nExpected: \2",
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


@dataclass
class _Assertion:
    result: InsoResult
    description: str
    reason: str
    preview: str = ""
    preview_shown: bool = False
    shown: bool = False
    reason_shown: bool = False


@dataclass
class _RequestGroup:
    execution: RequestExecution | None
    assertions: list[_Assertion]
    label: str
    row: str
    headers: str
    counts: dict[InsoStatus, int]
    row_shown: bool = False
    headers_shown: bool = False
    selected_counts: dict[InsoStatus, int] = field(default_factory=dict)

    def selected(self, status: InsoStatus) -> list[_Assertion]:
        return [a for a in self.assertions if a.result.status == status and a.shown]

    def omissions(self, statuses: tuple[InsoStatus, ...]) -> str:
        parts = []
        for status in statuses:
            missing = sum(
                a.result.status == status and not a.shown for a in self.assertions
            )
            if missing:
                parts.append(
                    f"{missing} {_STATUS_LABELS[status]} {_plural(missing, 'assertion')} omitted"
                )
        reasons = sum(
            a.result.status in statuses
            and a.shown
            and bool(a.reason)
            and not a.reason_shown
            for a in self.assertions
        )
        if reasons:
            parts.append(f"{reasons} assertion {_plural(reasons, 'reason')} omitted")
        return "; ".join(parts)


def _plural(count: int, singular: str) -> str:
    return singular if count == 1 else singular + "s"


def _table_code(value: str) -> str:
    text = escape(_bounded_text(" ".join(value.split()), _MAX_NAME_BYTES), quote=False)
    text = re.sub(r"[\\`*_\[\]!~|@#]", lambda match: f"&#{ord(match[0])};", text)
    return f"<code>{text}</code>"


def _table_text(value: str) -> str:
    text = escape(_bounded_text(" ".join(value.split()), _MAX_NAME_BYTES), quote=False)
    return re.sub(r"[\\`*_\[\]!~|@#.:]", lambda match: f"&#{ord(match[0])};", text)


def _failure_preview(result: InsoResult, *, native: bool) -> str:
    message = _display_message(result.message or "") if native else result.message or ""
    lines = message.splitlines()
    preview = lines[0] if lines else "No failure reason provided"
    return _table_text(preview)


def _disclosure(label: str, body: str) -> str:
    return f"<details><summary>{label}</summary>\n\n{body}" + _DETAILS_CLOSE


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
        if matches is None:
            unattributed.append(result)
        else:
            matches.append(result)
    groups: list[tuple[RequestExecution | None, list[InsoResult]]] = [
        (execution, grouped[execution.id]) for execution in report.executions
    ]
    if unattributed:
        groups.append((None, unattributed))
    return sorted(
        groups, key=lambda group: not any(r.status == InsoStatus.FAIL for r in group[1])
    )


def _request_counts(results: list[InsoResult]) -> str:
    return " | ".join(
        str(sum(r.status == status for r in results))
        for status in (InsoStatus.PASS, InsoStatus.FAIL, InsoStatus.SKIP)
    )


def _request_response(execution: RequestExecution) -> str:
    response = []
    if execution.status_code is not None:
        status = (
            " " + _bounded_text(" ".join(execution.status.split()), _MAX_NAME_BYTES)
            if execution.status
            else ""
        )
        response.append(_table_code(f"HTTP {execution.status_code}{status}"))
    elif execution.status:
        response.append(_table_code(execution.status))
    else:
        response.append("Unknown")
    if execution.duration_seconds is not None:
        response.append(escape(_duration(execution.duration_seconds)))
    return _LINE_BREAK.join(response)


def _request_identity(
    execution: RequestExecution, *, repeated: bool
) -> tuple[str, str]:
    context = []
    if repeated:
        context.append(f"Execution {execution.id}")
    if execution.iteration is not None:
        context.append(f"Iteration {execution.iteration + 1}")
    label = f"\n**{_inline_code(execution.name)}**\n\n"
    name = _table_code(execution.name)
    if context:
        label += "\n".join(context) + "\n\n"
        name += _LINE_BREAK + _LINE_BREAK.join(context)
    return name, label


def _make_assertion(result: InsoResult, name: str, *, native: bool) -> _Assertion:
    reason = ""
    if result.message:
        message = result.message
        if native:
            message = _display_message(message)
        reason = _literal_block(message)
    return _Assertion(
        result,
        f"| {name} | {_table_text(result.description)} | "
        if result.status == InsoStatus.FAIL
        else _result_block(result, include_message=False),
        reason,
        preview=_failure_preview(result, native=native)
        if result.status == InsoStatus.FAIL
        else "",
    )


def _make_group(
    execution: RequestExecution | None,
    results: list[InsoResult],
    *,
    native: bool,
    repeated: bool,
) -> _RequestGroup:
    label = "\n**Assertions without request details**\n\n"
    name = "Request details unavailable"
    row = headers = ""
    if execution is not None:
        name, label = _request_identity(execution, repeated=repeated)
        row = f"| {name} | {_request_counts(results)} | {_request_response(execution)} |\n"
        if execution.headers:
            headers = _literal_block(
                "\n".join(f"{k}: {v}" for k, v in execution.headers.items())
            )
    assertions = [_make_assertion(result, name, native=native) for result in results]
    return _RequestGroup(
        execution, assertions, label, row, headers, Counter(r.status for r in results)
    )


class _MarkdownReport:
    def __init__(self, report: InsoRunReport, prefix: str, footer: str, raw: str):
        self.report, self.prefix, self.footer, self.raw = report, prefix, footer, raw
        repeated = {
            name
            for name, count in Counter(
                execution.name for execution in report.executions
            ).items()
            if count > 1
        }
        self.groups = [
            _make_group(
                execution,
                results,
                native=report.source == "native",
                repeated=bool(execution and execution.name in repeated),
            )
            for execution, results in _result_groups(report)
        ]
        self.raw_shown = False
        self.started: set[InsoStatus] = set()
        self.counts = {
            status: sum(
                a.result.status == status
                for group in self.groups
                for a in group.assertions
            )
            for status in InsoStatus
        }

    def _set_complete(self, complete: bool) -> None:
        self.raw_shown = complete and bool(self.raw)
        self.started = set(self.counts) if complete else set()
        for group in self.groups:
            group.row_shown = complete and bool(group.row)
            group.headers_shown = complete and bool(group.headers)
            group.selected_counts = dict(group.counts) if complete else {}
            for assertion in group.assertions:
                assertion.shown = complete
                assertion.preview_shown = complete and bool(assertion.preview)
                assertion.reason_shown = complete and bool(assertion.reason)

    def _assertion_section(self, status: InsoStatus) -> str:
        if status == InsoStatus.FAIL:
            return self._failed_assertions()
        blocks = []
        for group in self.groups:
            selected = group.selected(status)
            if not selected:
                continue
            blocks.append(group.label)
            for assertion in selected:
                blocks.append(assertion.description)
                if assertion.reason_shown:
                    blocks.extend(("\n", assertion.reason))
            omission = group.omissions((status,))
            if omission:
                blocks.append(
                    f"\n{omission} in this request. Use JSON or JUnit for complete evidence.\n\n"
                )
        if not blocks:
            return ""
        body = "".join(blocks)
        count = self.counts[status]
        return _disclosure(
            f"{_STATUS_LABELS[status].title()} {_plural(count, 'assertion')} ({count})",
            body,
        )

    def _failed_assertions(self) -> str:
        rows: list[str] = []
        notices = []
        for group in self.groups:
            selected = group.selected(InsoStatus.FAIL)
            if not selected:
                continue
            rows.extend(
                assertion.description
                + (assertion.preview if assertion.preview_shown else _OMITTED_PREVIEW)
                + " |\n"
                for assertion in selected
            )
            omission = group.omissions((InsoStatus.FAIL,))
            if omission:
                notices.append(
                    group.label
                    + f"\n{omission} in this request. Use JSON or JUnit for complete evidence.\n\n"
                )
        if not rows:
            return ""
        return _FAILURE_HEADER + "".join(rows) + "\n" + "".join(notices)

    def _failure_output(self) -> str:
        body = "".join(
            group.label
            + f"**{_inline_code(assertion.result.description)}**\n\n"
            + assertion.reason
            for group in self.groups
            for assertion in group.selected(InsoStatus.FAIL)
            if assertion.reason_shown
        )
        return _disclosure("Failure output", body) if body else ""

    def _overview(self) -> str:
        if not self.report.executions:
            return ""
        rows = [group.row for group in self.groups if group.row_shown]
        if not rows:
            return ""
        table = _OVERVIEW_HEADER + "".join(rows) + "\n"
        total = len(self.report.executions)
        if total > 10:
            return _disclosure(f"View requests ({total})", table)
        return "### Requests\n\n" + table

    def _headers(self) -> str:
        body = "".join(
            group.label + group.headers for group in self.groups if group.headers_shown
        )
        return _disclosure("Captured response headers", body) if body else ""

    def _omissions(self) -> str:
        missing = []
        for status in (InsoStatus.FAIL, InsoStatus.SKIP, InsoStatus.PASS):
            count = sum(
                a.result.status == status and not a.shown
                for group in self.groups
                for a in group.assertions
            )
            if count:
                missing.append(
                    f"{count} {_STATUS_LABELS[status]} {_plural(count, 'assertion')}"
                )
        groups = sum(bool(group.row) and not group.row_shown for group in self.groups)
        if groups:
            missing.append(f"{groups} request {_plural(groups, 'group')}")
        headers = sum(
            bool(group.headers) and not group.headers_shown for group in self.groups
        )
        if headers:
            missing.append(f"{headers} response header {_plural(headers, 'group')}")
        if self.raw and not self.raw_shown:
            missing.append("raw diagnostics")
        if not missing:
            return ""
        return (
            "**Details omitted:**\n\n"
            + "".join(f"- {part} omitted.\n" for part in missing)
            + "\nUse JSON or JUnit for complete assertion evidence.\n\n"
        )

    def render(self) -> str:
        return (
            self.prefix
            + self._overview()
            + self._assertion_section(InsoStatus.FAIL)
            + self._failure_output()
            + self._assertion_section(InsoStatus.SKIP)
            + self._assertion_section(InsoStatus.PASS)
            + self._headers()
            + self._omissions()
            + self.footer
            + (self.raw if self.raw_shown else "")
        )

    def _description_cost(self, group: _RequestGroup, assertion: _Assertion) -> int:
        status = assertion.result.status
        cost = len(assertion.description.encode("utf-8"))
        if status == InsoStatus.FAIL:
            cost += len((_OMITTED_PREVIEW + " |\n").encode("utf-8"))
        if not group.selected_counts.get(status):
            # Reserve the largest local omission notice before adding this group.
            count = group.counts[status]
            reserve = f"\n{count} {_STATUS_LABELS[status]} assertions omitted; {count} assertion reasons omitted in this request. Use JSON or JUnit for complete evidence.\n\n"
            cost += len((group.label + reserve).encode("utf-8"))
        if status not in self.started:
            count = self.counts[status]
            frame = (
                _FAILURE_HEADER + "\n"
                if status == InsoStatus.FAIL
                else _disclosure(
                    f"{_STATUS_LABELS[status].title()} {_plural(count, 'assertion')} ({count})",
                    "",
                )
            )
            cost += len(frame.encode("utf-8"))
        return cost

    def _select_descriptions(self, status: InsoStatus, remaining: int) -> int:
        for group in self.groups:
            for assertion in group.assertions:
                if assertion.result.status != status:
                    continue
                cost = self._description_cost(group, assertion)
                if cost <= remaining:
                    assertion.shown = True
                    group.selected_counts[status] = (
                        group.selected_counts.get(status, 0) + 1
                    )
                    self.started.add(status)
                    remaining -= cost
        return remaining

    def _select_previews(self, remaining: int) -> int:
        for group in self.groups:
            for assertion in group.selected(InsoStatus.FAIL):
                cost = len(assertion.preview.encode("utf-8")) - len(_OMITTED_PREVIEW)
                if cost <= remaining:
                    assertion.preview_shown = True
                    remaining -= cost
        return remaining

    @staticmethod
    def _reason_frame(
        group: _RequestGroup, assertion: _Assertion, *, first: bool
    ) -> str:
        if assertion.result.status != InsoStatus.FAIL:
            return "\n"
        frame = group.label + f"**{_inline_code(assertion.result.description)}**\n\n"
        if first:
            frame += _disclosure("Failure output", "")
        return frame

    def _select_reasons(self, status: InsoStatus, remaining: int) -> int:
        first = True
        for group in self.groups:
            for assertion in group.selected(status):
                if not assertion.reason:
                    continue
                frame = self._reason_frame(group, assertion, first=first)
                block = _literal_block(
                    _display_message(assertion.result.message or "")
                    if self.report.source == "native"
                    else assertion.result.message or "",
                    max_bytes=remaining - len(frame.encode("utf-8")),
                )
                if block:
                    assertion.reason = block
                    assertion.reason_shown = True
                    remaining -= len((frame + block).encode("utf-8"))
                    first = False
        return remaining

    def _select_overview(self, remaining: int) -> int:
        total = len(self.report.executions)
        frame = _OVERVIEW_HEADER + "\n"
        frame = (
            _disclosure(f"View requests ({total})", frame)
            if total > 10
            else "### Requests\n\n" + frame
        )
        first = True
        for group in self.groups:
            if not group.row:
                continue
            cost = len((group.row + (frame if first else "")).encode("utf-8"))
            if cost <= remaining:
                group.row_shown = True
                remaining -= cost
                first = False
        return remaining

    def _select_headers(self, remaining: int) -> int:
        first = True
        for group in self.groups:
            if not group.headers:
                continue
            frame = _disclosure("Captured response headers", "") if first else ""
            available = remaining - len((frame + group.label).encode("utf-8"))
            block = (
                _literal_block(
                    "\n".join(f"{k}: {v}" for k, v in group.execution.headers.items()),
                    max_bytes=available,
                )
                if group.execution
                else ""
            )
            if block:
                group.headers = block
                group.headers_shown = True
                remaining -= len((frame + group.label + block).encode("utf-8"))
                first = False
        return remaining

    def bounded(self, budget: int) -> str:
        self._set_complete(True)
        complete = self.render()
        if len(complete.encode("utf-8")) <= budget:
            return complete
        self._set_complete(False)
        remaining = budget - len(self.render().encode("utf-8"))
        if remaining < 0:
            status, _ = _report_status(self.report)
            return _bounded_text(
                f"Insomnia {status}: {self.report.total_tests} assertions, {self.report.failed_count} failed. Details omitted; use JSON or JUnit output.",
                budget,
            )
        remaining = self._select_descriptions(InsoStatus.FAIL, remaining)
        remaining = self._select_overview(remaining)
        remaining = self._select_previews(remaining)
        remaining = self._select_reasons(InsoStatus.FAIL, remaining)
        for status in (InsoStatus.SKIP, InsoStatus.PASS):
            remaining = self._select_descriptions(status, remaining)
            remaining = self._select_reasons(status, remaining)
        remaining = self._select_headers(remaining)
        self.raw_shown = bool(self.raw) and len(self.raw.encode("utf-8")) <= remaining
        return self.render()


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
        status, icon = _report_status(report)
        lines = ["## Insomnia Run", ""]
        if report.target_name:
            lines.extend((f"**{_inline_code(report.target_name)}**", ""))
        requests = (
            str(report.request_count) if report.request_count is not None else "Unknown"
        )
        lines.extend(
            (
                f"{icon} **Result: {status}**",
                "",
                "| Requests | Assertions | Passed | Failed | Skipped |",
                "| ---: | ---: | ---: | ---: | ---: |",
                f"| {requests} | {report.total_tests} | {report.passed_count} | {report.failed_count} | {report.skipped_count} |",
                "",
            )
        )
        if report.request_count is None and report.run_type == RunType.COLLECTION:
            lines.extend(
                (
                    "Request details unavailable; recovered TAP may omit request details and assertion reasons.",
                    "",
                )
            )
        if not report.complete:
            lines.extend(("**Evidence:** Incomplete; completed results only.", ""))
        if not report.total_tests:
            lines.extend(("No assertions executed.", ""))
        error = report.evidence_error
        if error:
            lines.extend(
                ("### Run Error", "", error.kind, "", _literal_block(error.message))
            )
        return "\n".join(lines) + "\n"

    def generate_markdown(
        self,
        report: InsoRunReport,
        workflow_url: str | None = None,
        include_raw_output: bool = False,
        *,
        max_bytes: int = _MAX_MARKDOWN_BYTES,
    ) -> str:
        prefix = self._markdown_summary(report)
        link = _workflow_link(workflow_url)
        footer = (
            f"See the {link} for execution details and available report artifacts.\n\n"
            if link != "workflow run"
            else "Use JSON or JUnit output for complete assertion evidence.\n\n"
        )
        raw = ""
        if include_raw_output and report.raw_output and report.raw_output.strip():
            encoded = _xml_text(report.raw_output.strip()).encode("utf-8")
            text = encoded[:_MAX_RAW_OUTPUT_BYTES].decode("utf-8", errors="ignore")
            body = f"<pre><code>{escape(text, quote=False)}</code></pre>\n\n"
            if len(encoded) > _MAX_RAW_OUTPUT_BYTES:
                body += f"Raw output truncated at {_MAX_RAW_OUTPUT_BYTES} bytes.\n\n"
            raw = _disclosure("View raw output", body)
        return _MarkdownReport(report, prefix, footer, raw).bounded(max_bytes)

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
