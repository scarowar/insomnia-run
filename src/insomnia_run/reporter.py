import re
from html import escape

from .models import InsoRunReport, InsoStatus, RunType

DEFAULT_RAW_OUTPUT_MAX_BYTES = 8192
DEFAULT_MAX_ANNOTATIONS = 10
_MAX_RENDERED_RESULTS = 50
_XML_INVALID_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xml_safe(text: str) -> str:
    """Strip control characters that are illegal in XML 1.0."""
    return _XML_INVALID_CONTROL_CHARS.sub("", text)


def _xml_attrs(attrs: dict[str, str]) -> str:
    return " ".join(f'{name}="{escape(value, quote=True)}"' for name, value in attrs.items())


def _md_escape(text: str) -> str:
    """Escape HTML plus markdown structure (backticks, link/image brackets)."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("`", "\\`").replace("[", "\\[").replace("]", "\\]")


def _truncate(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    cut = encoded[:max_bytes].decode("utf-8", errors="ignore").rstrip()
    return f"{cut}\n... (output truncated at {max_bytes} bytes; full output in the report artifact)"


def _annotation_escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _code_fence(text: str) -> str:
    """A valid fence (min 3 backticks) longer than any backtick run inside."""
    longest_run = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            longest_run = max(longest_run, current)
        else:
            current = 0
    return "`" * max(3, longest_run + 1)


class Reporter:
    @staticmethod
    def _run_label(report: InsoRunReport) -> str:
        return "Collection" if report.run_type == RunType.COLLECTION else "Test Suite"

    def generate_markdown(
        self,
        report: InsoRunReport,
        *,
        workflow_url: str | None = None,
        include_raw_output: bool = True,
        raw_output_max_bytes: int = DEFAULT_RAW_OUTPUT_MAX_BYTES,
    ) -> str:
        lines = []

        run_label = self._run_label(report)
        executed_label = (
            "requests executed" if report.run_type == RunType.COLLECTION else "tests executed"
        )
        warned = bool(report.diagnostics) and report.failed_count == 0
        status = (
            "Failed" if report.failed_count else ("Passed with warnings" if warned else "Passed")
        )
        icon = "❌" if report.failed_count else ("⚠️" if warned else "✅")
        target = f": {_md_escape(report.target_name)}" if report.target_name else ""
        lines.append(f"## {icon} Insomnia {run_label} {status}{target}")
        lines.append("")

        lines.append("### Test Summary")
        lines.append("")
        if report.failed_count == 0 and report.skipped_count == 0:
            passed_text = "(all passed)"
        elif report.skipped_count > 0:
            passed_text = f"({report.passed_count} passed, {report.failed_count} failed, {report.skipped_count} skipped)"
        else:
            passed_text = f"({report.passed_count} passed, {report.failed_count} failed)"
        lines.append(f"- **{report.total_tests} {executed_label}** {passed_text}")
        if report.target_name:
            lines.append(f"- **Target:** `{_md_escape(report.target_name)}`")
        lines.append("")

        lines.append("### Test Results")
        lines.append("")
        rendered = report.results[:_MAX_RENDERED_RESULTS]
        for result in rendered:
            if result.status == InsoStatus.PASS:
                icon = "✅"
            elif result.status == InsoStatus.SKIP:
                icon = "⏭️"
            else:
                icon = "❌"
            lines.append(f"- {icon} **{_md_escape(result.description)}**")
            if result.status == InsoStatus.FAIL and result.message:
                lines.append(f"  - `{_md_escape(result.message)}`")
        hidden = len(report.results) - len(rendered)
        if hidden > 0:
            lines.append(
                f"- … and {hidden} more results (full details in the report artifact or JUnit output)"
            )
        lines.append("")

        if report.diagnostics:
            lines.append("### Diagnostics")
            lines.append("")
            for diagnostic in report.diagnostics:
                lines.append(f"- {_md_escape(diagnostic)}")
            lines.append("")

        lines.append("### Additional Information")
        lines.append("")
        if workflow_url:
            lines.append(f"Check the [workflow logs](<{workflow_url}>) for details")
        else:
            lines.append("Check the workflow logs for details")
        lines.append("")

        if include_raw_output and report.raw_output:
            truncated = _truncate(report.raw_output.strip(), raw_output_max_bytes)
            fence = _code_fence(truncated)
            lines.append("<details><summary>View raw output</summary>")
            lines.append("")
            lines.append(fence)
            lines.append(truncated)
            lines.append(fence)
            lines.append("</details>")

        return "\n".join(lines)

    def generate_junit(self, report: InsoRunReport) -> str:
        run_label = self._run_label(report)
        suite_name = f"Insomnia {run_label}"
        classname = report.target_name or suite_name
        suite_attrs = _xml_attrs(
            {
                "name": suite_name,
                "tests": str(report.total_tests),
                "failures": str(report.failed_count),
                "errors": "0",
                "skipped": str(report.skipped_count),
                "time": "0",
            }
        )
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', f"<testsuite {suite_attrs}>"]

        for result in report.results:
            description = _xml_safe(result.description)
            message = _xml_safe(result.message) if result.message else None
            testcase_attrs = _xml_attrs(
                {
                    "classname": classname,
                    "name": description,
                    "time": "0",
                }
            )

            if result.status == InsoStatus.FAIL:
                failure_attrs = _xml_attrs({"message": message or description})
                lines.append(f"  <testcase {testcase_attrs}>")
                lines.append(
                    f"    <failure {failure_attrs}>{escape(message or description)}</failure>"
                )
                lines.append("  </testcase>")
            elif result.status == InsoStatus.SKIP:
                lines.append(f"  <testcase {testcase_attrs}>")
                lines.append("    <skipped />")
                lines.append("  </testcase>")
            else:
                lines.append(f"  <testcase {testcase_attrs} />")

        lines.append("</testsuite>")
        return "\n".join(lines) + "\n"

    def annotations(
        self, report: InsoRunReport, max_annotations: int = DEFAULT_MAX_ANNOTATIONS
    ) -> list[str]:
        failing = [r for r in report.results if r.status == InsoStatus.FAIL]
        return [
            f"::error title={_annotation_escape(r.description)}"
            f"::{_annotation_escape(r.message or r.description)}"
            for r in failing[:max_annotations]
        ]
