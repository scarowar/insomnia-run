from .models import InsoRunReport, InsoStatus, RunType

class Reporter:
    def generate_markdown(self, report: InsoRunReport, workflow_url: str | None = None) -> str:
        lines = []
        
        run_label = "Collection" if report.run_type == RunType.COLLECTION else "Test Suite"
        status = "Passed" if report.failed_count == 0 else "Failed"
        icon = "✅" if report.failed_count == 0 else "❌"
        target = f": {report.target_name}" if report.target_name else ""
        lines.append(f"## {icon} Insomnia {run_label} {status}{target}")
        lines.append("")
        
        lines.append("### Test Summary")
        lines.append("")
        passed_text = "(all passed)" if report.failed_count == 0 else f"({report.passed_count} passed, {report.failed_count} failed)"
        lines.append(f"- **{report.total_tests} requests executed** {passed_text}")
        if report.target_name:
            lines.append(f"- **Target:** `{report.target_name}`")
        lines.append("")
        
        lines.append("### Test Results")
        lines.append("")
        for result in report.results:
            icon = "✅" if result.status == InsoStatus.PASS else "❌"
            lines.append(f"- {icon} **{result.description}**")
        lines.append("")
        
        lines.append("### Additional Information")
        lines.append("")
        if workflow_url:
            lines.append(f"Check the [workflow logs]({workflow_url}) for details")
        else:
            lines.append("Check the workflow logs for details")
        lines.append("")
        
        if report.raw_output:
            lines.append("<details><summary>View raw output</summary>")
            lines.append("")
            lines.append("```")
            lines.append(report.raw_output.strip())
            lines.append("```")
            lines.append("</details>")
        
        return "\n".join(lines)