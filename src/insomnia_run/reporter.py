import re
from xml.etree import ElementTree  # nosec B405 - only creates and serializes XML.

from .models import InsoRunReport, InsoStatus, RunType


class Reporter:
    @staticmethod
    def _run_label(report: InsoRunReport) -> str:
        return "Collection" if report.run_type == RunType.COLLECTION else "Test Suite"

    @staticmethod
    def _xml_text(value: str) -> str:
        # XML 1.0 forbids some characters that are valid in Python strings.
        return re.sub(
            r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]",
            "\ufffd",
            value,
        )

    def generate_markdown(
        self,
        report: InsoRunReport,
        workflow_url: str | None = None,
        include_raw_output: bool = False,
    ) -> str:
        lines = []

        run_label = self._run_label(report)
        if report.failed_count:
            status, icon = "Failed", "❌"
        elif not report.total_tests:
            status, icon = "No Assertions Executed", "⏭️"
        elif report.skipped_count == report.total_tests:
            status, icon = "Skipped", "⏭️"
        else:
            status, icon = "Passed", "✅"
        target = f": {report.target_name}" if report.target_name else ""
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
            lines.append(f"- **Target:** `{report.target_name}`")
        lines.extend(["", "### Test Results", ""])
        for result in report.results:
            if result.status == InsoStatus.PASS:
                icon = "✅"
            elif result.status == InsoStatus.SKIP:
                icon = "⏭️"
            else:
                icon = "❌"
            lines.append(f"- {icon} **{result.description}**")
        lines.extend(["", "### Additional Information", ""])
        if workflow_url:
            lines.append(
                f"See the [workflow run]({workflow_url}) for execution details."
            )
        else:
            lines.append("See the workflow run for execution details.")
        if not include_raw_output:
            lines.append(
                "Raw Inso diagnostics are omitted. Enable `include-raw-output` "
                "(CLI: `--include-raw-output`) only when safe: diagnostics can "
                "contain secrets."
            )
        lines.append("")

        if include_raw_output and report.raw_output:
            lines.extend(
                [
                    "<details><summary>View raw output</summary>",
                    "",
                    "```",
                    report.raw_output.strip(),
                    "```",
                    "</details>",
                ]
            )

        return "\n".join(lines)

    def generate_junit(self, report: InsoRunReport) -> str:
        run_label = self._run_label(report)
        suite_name = f"Insomnia {run_label}"
        classname = self._xml_text(report.target_name or suite_name)
        suite = ElementTree.Element(
            "testsuite",
            {
                "name": suite_name,
                "tests": str(report.total_tests),
                "failures": str(report.failed_count),
                "errors": "0",
                "skipped": str(report.skipped_count),
                "time": "0",
            },
        )
        for result in report.results:
            description = self._xml_text(result.description)
            testcase = ElementTree.SubElement(
                suite,
                "testcase",
                {
                    "classname": classname,
                    "name": description,
                    "time": "0",
                },
            )

            if result.status == InsoStatus.FAIL:
                failure = ElementTree.SubElement(
                    testcase, "failure", {"message": description}
                )
                failure.text = "Inso reported this test as failed."
            elif result.status == InsoStatus.SKIP:
                ElementTree.SubElement(testcase, "skipped")

        ElementTree.indent(suite, space="  ")
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            + ElementTree.tostring(suite, encoding="unicode")
            + "\n"
        )
