from html import escape

from .models import InsoRunReport, InsoStatus, RunType


class Reporter:
    @staticmethod
    def _run_label(report: InsoRunReport) -> str:
        return "Collection" if report.run_type == RunType.COLLECTION else "Test Suite"

    @staticmethod
    def _xml_attrs(attrs: dict[str, str]) -> str:
        return " ".join(
            f'{name}="{escape(value, quote=True)}"' for name, value in attrs.items()
        )

    def generate_markdown(
        self,
        report: InsoRunReport,
        workflow_url: str | None = None,
        include_raw_output: bool = False,
    ) -> str:
        lines = []

        run_label = self._run_label(report)
        status = "Passed" if report.failed_count == 0 else "Failed"
        icon = "✅" if report.failed_count == 0 else "❌"
        target = f": {report.target_name}" if report.target_name else ""
        lines.append(f"## {icon} Insomnia {run_label} {status}{target}")
        lines.append("")

        lines.append("### Test Summary")
        lines.append("")
        if report.failed_count == 0 and report.skipped_count == 0:
            passed_text = "(all passed)"
        elif report.skipped_count > 0:
            passed_text = f"({report.passed_count} passed, {report.failed_count} failed, {report.skipped_count} skipped)"
        else:
            passed_text = (
                f"({report.passed_count} passed, {report.failed_count} failed)"
            )
        lines.append(f"- **{report.total_tests} requests executed** {passed_text}")
        if report.target_name:
            lines.append(f"- **Target:** `{report.target_name}`")
        lines.append("")

        lines.append("### Test Results")
        lines.append("")
        for result in report.results:
            if result.status == InsoStatus.PASS:
                icon = "✅"
            elif result.status == InsoStatus.SKIP:
                icon = "⏭️"
            else:
                icon = "❌"
            lines.append(f"- {icon} **{result.description}**")
        lines.append("")

        lines.append("### Additional Information")
        lines.append("")
        if workflow_url:
            lines.append(f"Check the [workflow logs]({workflow_url}) for details")
        else:
            lines.append("Check the workflow logs for details")
        lines.append("")

        if include_raw_output and report.raw_output:
            lines.append("<details><summary>View raw output</summary>")
            lines.append("")
            lines.append("```")
            lines.append(report.raw_output.strip())
            lines.append("```")
            lines.append("</details>")

        return "\n".join(lines)

    def generate_junit(self, report: InsoRunReport) -> str:
        run_label = self._run_label(report)
        suite_name = f"Insomnia {run_label}"
        classname = report.target_name or suite_name
        suite_attrs = self._xml_attrs(
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
            testcase_attrs = self._xml_attrs(
                {
                    "classname": classname,
                    "name": result.description,
                    "time": "0",
                }
            )

            if result.status == InsoStatus.FAIL:
                failure_attrs = self._xml_attrs({"message": result.description})
                lines.append(f"  <testcase {testcase_attrs}>")
                lines.append(
                    f"    <failure {failure_attrs}>"
                    "Inso reported this test as failed."
                    "</failure>"
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
