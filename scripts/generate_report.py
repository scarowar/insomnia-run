import os
import re
import sys
import json
from pathlib import Path
from typing import Any, Dict, Tuple, List

# --- Logging Helpers ---
def log_debug(msg: str) -> None:
    if os.environ.get("DEBUG", "false").lower() == "true":
        print(f"::debug::{msg}")

def log_info(msg: str) -> None:
    print(msg)

def log_warning(msg: str) -> None:
    print(f"::warning::{msg}")

def log_section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")

def error_exit(message: str) -> None:
    print(f"::error::{message}")
    sys.exit(1)

def _parse_suite_line(line: str) -> str:
    match = re.match(r'»\s*(.+?)\.', line)
    return match.group(1).strip() if match else None

def _parse_passed_line(line: str) -> str:
    match = re.match(r'[✓✅]\s*(.+)', line)
    return match.group(1).strip() if match else None

def _parse_failed_line(line: str) -> str:
    match = re.match(r'[✖❌]\s*(.+)', line)
    return match.group(1).strip() if match else None

def _extract_failure_details(lines: List[str], start_idx: int) -> Tuple[str, str]:
    """Extracts the failed test name and error message from lines starting at start_idx."""
    test_name = _parse_failed_line(lines[start_idx])
    error_lines = []
    for j in range(start_idx + 1, len(lines)):
        next_line = lines[j].strip()
        if not next_line or re.match(r'✓\s*|✖\s*|»\s*', next_line):
            break
        error_lines.append(next_line)
    error_msg = "\n".join(error_lines).strip()
    return test_name, error_msg

def parse_inso_output(output: str) -> Dict[str, Any]:
    """
    Parses the 'spec' reporter output from inso CLI.
    Args:
        output (str): The raw output from inso CLI.
    Returns:
        Dict[str, Any]: Parsed results including totals, per-suite, and failures.
    """
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "failures": [],
        "suites": {}
    }
    current_suite = "General"
    lines = output.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        suite_name = _parse_suite_line(line)
        if suite_name:
            current_suite = suite_name
            if current_suite not in results["suites"]:
                results["suites"][current_suite] = {"passed": 0, "failed": 0, "tests": []}
            i += 1
            continue
        test_name = _parse_passed_line(line)
        if test_name:
            results["total"] += 1
            results["passed"] += 1
            if current_suite not in results["suites"]:
                results["suites"][current_suite] = {"passed": 0, "failed": 0, "tests": []}
            results["suites"][current_suite]["passed"] += 1
            results["suites"][current_suite]["tests"].append({"name": test_name, "status": "passed"})
            i += 1
            continue
        if _parse_failed_line(line):
            test_name, error_msg = _extract_failure_details(lines, i)
            results["total"] += 1
            results["failed"] += 1
            if current_suite not in results["suites"]:
                results["suites"][current_suite] = {"passed": 0, "failed": 0, "tests": []}
            results["suites"][current_suite]["failed"] += 1
            failure_details = {"name": test_name, "status": "failed", "suite": current_suite, "error": error_msg}
            results["failures"].append(failure_details)
            results["suites"][current_suite]["tests"].append(failure_details)
            # Skip error lines
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if not next_line or re.match(r'✓\s*|✖\s*|»\s*', next_line):
                    break
                j += 1
            i = j
            continue
        i += 1
    return results

def _format_suite_details(suite: str, data: Dict[str, Any]) -> str:
    suite_status_emoji = "✅" if data["failed"] == 0 else "❌"
    details = f"#### {suite_status_emoji} Suite: `{suite}` ({data['passed']} Passed, {data['failed']} Failed)\n"
    details += "```\n"
    for test in data["tests"]:
        status_char = "✓" if test["status"] == "passed" else "✖"
        details += f"{status_char} {test['name']}\n"
        if test["status"] == "failed" and test["error"]:
            details += f"  Error: {test['error']}\n"
    details += "```\n"
    return details

def format_markdown_report(
    parsed_results: Dict[str, Any],
    command: str,
    identifier: str,
    pr_comment_title: str,
    exit_code: int,
    raw_output: str,
) -> Tuple[str, str]:
    """
    Formats the test results into a Markdown string for a PR comment.
    Returns the markdown and the overall status.
    """
    status_emoji = "✅" if parsed_results["failed"] == 0 and exit_code == 0 else "❌"
    overall_status = "PASSED" if parsed_results["failed"] == 0 and exit_code == 0 else "FAILED"
    report_content = f"## {pr_comment_title}\n\n"
    report_content += f"{status_emoji} **Insomnia {command.replace('run ', '').replace('lint ', '').title()} Status: {overall_status}** for `{identifier}`\n\n"
    report_content += "### Summary\n"
    report_content += "| Metric      | Count |\n"
    report_content += "|-------------|-------|\n"
    report_content += f"| Total       | {parsed_results['total']}   |\n"
    report_content += f"| Passed      | {parsed_results['passed']}   |\n"
    report_content += f"| Failed      | {parsed_results['failed']}   |\n"
    report_content += "\n"
    if parsed_results["failed"] > 0:
        report_content += "### Failed Details 🕵️\n"
        report_content += "| Suite | Test Name | Error |\n"
        report_content += "|-------|-----------|-------|\n"
        for failure in parsed_results["failures"]:
            error_msg = failure["error"].replace('\n', ' ').replace('|', '\|')
            report_content += f"| `{failure['suite']}` | `{failure['name']}` | `{error_msg}` |\n"
        report_content += "\n"
    report_content += "<details><summary>Detailed Test Results by Suite 📚</summary>\n\n"
    for suite, data in parsed_results["suites"].items():
        report_content += _format_suite_details(suite, data)
    report_content += "</details>\n\n"
    report_content += "<details><summary>Raw Inso CLI Output 📜</summary>\n\n"
    report_content += "```\n" + raw_output + "\n```\n"
    report_content += "</details>"
    return report_content, overall_status

def main() -> None:
    """
    Main entry point for the Insomnia Action report generator.
    Validates environment, parses output, writes artifacts, and logs summary.
    """
    log_section("🚦 Insomnia Action Report Generation Start")
    # Validate required environment variables

    required_envs = [
        "INSO_RAW_OUTPUT", "INSO_EXIT_CODE", "INPUT_COMMAND_RAN", "INPUT_IDENTIFIER_RAN", "GITHUB_OUTPUT"
    ]
    missing = [e for e in required_envs if not os.environ.get(e)]
    if missing:
        error_exit(f"Missing required environment variables: {', '.join(missing)}")

    inso_raw_output = os.environ["INSO_RAW_OUTPUT"]
    try:
        inso_exit_code = int(os.environ["INSO_EXIT_CODE"])
    except Exception:
        error_exit("INSO_EXIT_CODE must be an integer.")

    command_ran = os.environ["INPUT_COMMAND_RAN"]
    identifier_ran = os.environ["INPUT_IDENTIFIER_RAN"]
    github_output = os.environ["GITHUB_OUTPUT"]

    log_debug(f"Parsing inso output for command: {command_ran}, identifier: {identifier_ran}")
    parsed_results = parse_inso_output(inso_raw_output)

    # Use a default PR comment title
    pr_comment_title = "Insomnia Test Results"
    comment_body, overall_status = format_markdown_report(
        parsed_results, command_ran, identifier_ran, pr_comment_title, inso_exit_code, inso_raw_output
    )

    # Write markdown report to file for artifact upload
    report_path = os.environ.get("REPORT_PATH", "insomnia_report.md")
    try:
        with open(report_path, "w") as f:
            f.write(comment_body)
        log_info(f"📝 Markdown report written to {report_path}")
    except Exception as e:
        error_exit(f"Failed to write markdown report: {e}")

    # Write parsed results as JSON for automation
    json_path = os.environ.get("JSON_REPORT_PATH", "insomnia_report.json")
    try:
        with open(json_path, "w") as jf:
            json.dump(parsed_results, jf, indent=2)
        log_info(f"📝 JSON report written to {json_path}")
    except Exception as e:
        error_exit(f"Failed to write JSON report: {e}")

    # Set GitHub Action outputs (standardized keys)
    with open(github_output, 'a') as out:
        out.write(f"summary={overall_status}\n")
        out.write(f"comment_body<<EOF\n{comment_body}\nEOF\n")
        out.write(f"report_path={report_path}\n")
        out.write(f"json_report_path={json_path}\n")

    log_section("✅ Report generation complete.")

if __name__ == "__main__":
    main()