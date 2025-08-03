#!/usr/bin/env python3
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# Constants for commonly used regex patterns
PASSING_FAILING_PATTERN = re.compile(r"^\d+\s+(passing|failing)")
ERROR_PREFIX = "error:"

# ANSI escape sequence patterns (compiled once for performance)
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
BRACKET_CODES_PATTERN = re.compile(r"\[[0-9;]*m")

# Additional compiled patterns for performance
TEST_RESULTS_PATTERN = re.compile(
    r"^(Test results?|Tests?:|Test Requests?|Error:|Warning:|Total:|Summary)",
    re.IGNORECASE,
)
ANALYSIS_KEYWORDS_PATTERN = re.compile(r"\b(Analysis|Summary|Total)\b", re.IGNORECASE)
PASSED_TEST_PATTERN = re.compile(r"^\s*[✓✔✅]\s*(.*?)(?:\s\((\d+)ms\))?$")
FAILED_TEST_PATTERN = re.compile(r"^\s*[✗✖❌]\s*(.*)$")
TEST_STATUS_SYMBOLS_PATTERN = re.compile(r"^\s*[✓✔✅✗✖❌]")
ANSI_SUMMARY_PATTERN = re.compile(r"^\[[0-9;]*m.*\[[0-9;]*m.*total")
TEST_HEADER_PATTERN = re.compile(r"^Test(s)?:\s+")
TEST_REQUESTS_PATTERN = re.compile(r"^Test Requests?:\s+")
SUITE_LINE_PATTERN = re.compile(
    r"^\s{2,}(?![\s✓✗✔❌✅✖]|Error|at\s|Expected|AssertionError|TypeError|ReferenceError)([A-Za-z][\w\s.-]+)$"
)
SUITE_LEGACY_PATTERN = re.compile(r"^»\s*(.+?)\.")

# Line exclusion prefixes for suite parsing
EXCLUDED_LINE_PREFIXES = (
    "Error:",
    "at ",
    "Expected",
    "AssertionError",
    "TypeError",
    "ReferenceError",
    "Total:",
)


def log_debug(msg: str) -> None:
    """Log debug message if DEBUG environment variable is set."""
    if os.environ.get("DEBUG", "false").lower() == "true":
        print(f"::debug::{msg}")


def log_info(msg: str) -> None:
    """Log informational message."""
    print(msg)


def log_warning(msg: str) -> None:
    """Log warning message."""
    print(f"::warning::{msg}")


def log_section(title: str) -> None:
    """Log section header for better output organization."""
    print(f"\n{title}\n{'-' * len(title)}")


def error_exit(message: str) -> None:
    """Log error and exit with non-zero status."""
    print(f"::error::{message}")
    sys.exit(1)


def _get_success_rate_emoji(success_rate: float) -> str:
    """Return appropriate emoji for success rate."""
    if success_rate == 100:
        return "🏆"
    elif success_rate >= 80:
        return "📈"
    elif success_rate >= 70:
        return "⚠️"
    else:
        return "💥"


def _strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI color codes and formatting from text.

    Args:
        text: Text potentially containing ANSI codes

    Returns:
        Clean text without ANSI codes
    """
    # Remove ANSI escape sequences using pre-compiled patterns
    text = ANSI_ESCAPE_PATTERN.sub("", text)
    text = BRACKET_CODES_PATTERN.sub("", text)
    return text


def _should_exclude_line(stripped_line: str) -> bool:
    """
    Check if a line should be excluded from suite parsing.

    Args:
        stripped_line: Line content with whitespace stripped

    Returns:
        True if the line should be excluded, False otherwise
    """
    # Skip summary lines like "1 passing (264ms)", "Test results:", etc.
    if PASSING_FAILING_PATTERN.match(stripped_line):
        return True

    if TEST_RESULTS_PATTERN.match(stripped_line):
        return True

    # Skip lines that look like error messages, stack traces, or analysis content
    if stripped_line.startswith(EXCLUDED_LINE_PREFIXES):
        return True

    # Skip lines that contain analysis keywords
    if ANALYSIS_KEYWORDS_PATTERN.search(stripped_line):
        return True

    return False


def _parse_suite_line(line: str) -> Optional[str]:
    """
    Parse suite/collection names from Insomnia CLI output.

    Args:
        line: A single line from the CLI output

    Returns:
        Suite name if found, None otherwise

    Note:
        Excludes summary lines, error messages, and non-suite content
    """
    stripped = line.strip()

    # Use helper function to check if line should be excluded
    if _should_exclude_line(stripped):
        return None

    # Only match lines that are indented (typically 2 spaces) but don't start with test status symbols
    suite_regexes = [
        SUITE_LINE_PATTERN,  # Indented, not a status symbol
        SUITE_LEGACY_PATTERN,  # Legacy/alt format
    ]

    for regex in suite_regexes:
        match = regex.match(line)
        if match:
            suite_name = match.group(1).strip()
            # Use helper function for additional filtering
            if not _should_exclude_line(suite_name) and len(suite_name) > 0:
                return suite_name
    return None


def _parse_passed_line(line: str) -> str:
    """
    Extract test name from a passed test line.

    Args:
        line: CLI output line potentially containing a passed test

    Returns:
        Test name if line represents a passed test, None otherwise
    """
    match = PASSED_TEST_PATTERN.match(line)
    return match.group(1).strip() if match else None


def _parse_failed_line(line: str) -> str:
    """
    Extract test name from a failed test line.

    Args:
        line: CLI output line potentially containing a failed test

    Returns:
        Test name if line represents a failed test, None otherwise
    """
    match = FAILED_TEST_PATTERN.match(line)
    return match.group(1).strip() if match else None


def _is_test_result_line(line: str) -> bool:
    """Check if line is a test result or suite line."""
    # Check for test result lines with status symbols
    if TEST_STATUS_SYMBOLS_PATTERN.match(line):
        return True

    # Check for suite lines: indented (2+ spaces) but not starting with status symbols or error indicators
    # More specific than just "any letter" - exclude common error/debug prefixes
    if SUITE_LINE_PATTERN.match(line):
        return True

    return False


def _is_summary_or_header_line(line: str) -> bool:
    """Check if line is a summary or header line that indicates end of error details."""
    return bool(
        ANSI_SUMMARY_PATTERN.match(line)  # ANSI summary lines
        or TEST_HEADER_PATTERN.match(line)
        or TEST_REQUESTS_PATTERN.match(line)
        or PASSING_FAILING_PATTERN.match(line)
    )


def _extract_error_from_line(line: str) -> Optional[str]:
    """Extract clean error message from a line if it contains an error."""
    if not line.startswith(ERROR_PREFIX):
        return None

    clean_error = _strip_ansi_codes(line)
    clean_error = clean_error.replace(ERROR_PREFIX, "").strip()
    return clean_error if clean_error else None


def _collect_immediate_error_lines(lines: List[str], start_idx: int) -> List[str]:
    """Collect error lines immediately following a failed test."""
    error_lines = []

    for j in range(start_idx + 1, len(lines)):
        next_line = lines[j].strip()
        if not next_line:
            continue

        # Stop if we hit another test result or suite
        if _is_test_result_line(next_line):
            break

        # Stop if we hit summary lines
        if _is_summary_or_header_line(next_line):
            break

        # Include actual error lines
        clean_error = _extract_error_from_line(next_line)
        if clean_error and clean_error not in error_lines:
            error_lines.append(clean_error)

    return error_lines


def _collect_fallback_error_lines(lines: List[str]) -> List[str]:
    """Collect error lines from entire output as fallback."""
    error_lines = []
    for line in lines:
        clean_error = _extract_error_from_line(line.strip())
        if clean_error and clean_error not in error_lines:
            error_lines.append(clean_error)
    return error_lines


def _extract_failure_details(lines: List[str], start_idx: int) -> Tuple[str, str]:
    """
    Extract failure details including test name and error message.

    Args:
        lines: All CLI output lines
        start_idx: Index of the failed test line

    Returns:
        Tuple of (test_name, error_message)
    """
    test_name = _parse_failed_line(lines[start_idx])

    # First try to get errors immediately following the failed test
    error_lines = _collect_immediate_error_lines(lines, start_idx)

    # If no specific errors found, look for them in the entire output
    if not error_lines:
        error_lines = _collect_fallback_error_lines(lines)

    error_msg = "\n".join(error_lines).strip()
    return test_name, error_msg


def _initialize_suite_if_needed(results: Dict[str, Any], suite_name: str) -> None:
    """Initialize suite in results if it doesn't exist."""
    if suite_name not in results["suites"]:
        results["suites"][suite_name] = {
            "passed": 0,
            "failed": 0,
            "tests": [],
        }


def _process_passed_test(
    results: Dict[str, Any], test_name: str, current_suite: str
) -> None:
    """Process a passed test and update results."""
    results["total"] += 1
    results["passed"] += 1
    _initialize_suite_if_needed(results, current_suite)
    results["suites"][current_suite]["passed"] += 1
    results["suites"][current_suite]["tests"].append(
        {"name": test_name, "status": "passed"}
    )


def _process_failed_test(
    results: Dict[str, Any], test_name: str, current_suite: str, error_msg: str
) -> None:
    """Process a failed test and update results."""
    results["total"] += 1
    results["failed"] += 1
    _initialize_suite_if_needed(results, current_suite)
    results["suites"][current_suite]["failed"] += 1

    failure_details = {
        "name": test_name,
        "status": "failed",
        "suite": current_suite,
        "error": error_msg,
    }
    results["failures"].append(failure_details)
    results["suites"][current_suite]["tests"].append(failure_details)


def parse_inso_output(output: str) -> Dict[str, Any]:
    """
    Parse Insomnia CLI spec reporter output into structured data.

    Args:
        output: Raw text output from inso CLI with --reporter spec

    Returns:
        Dictionary containing:
        - total: Total number of tests/requests
        - passed: Number of passed tests/requests
        - failed: Number of failed tests/requests
        - failures: List of failure details
        - suites: Per-suite breakdown of results

    Raises:
        ValueError: If output format is unrecognizable
    """
    results = {"total": 0, "passed": 0, "failed": 0, "failures": [], "suites": {}}
    current_suite = "General"
    lines = output.splitlines()

    # Extract all error messages first
    all_errors = _collect_fallback_error_lines(lines)
    error_index = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        # Check for suite line
        suite_name = _parse_suite_line(line)
        if suite_name:
            current_suite = suite_name
            _initialize_suite_if_needed(results, current_suite)
            i += 1
            continue

        # Check for passed test
        test_name = _parse_passed_line(line)
        if test_name:
            _process_passed_test(results, test_name, current_suite)
            i += 1
            continue

        # Check for failed test
        failed_test_name = _parse_failed_line(line)
        if failed_test_name:
            # Get error message with validation
            if error_index < len(all_errors):
                error_msg = all_errors[error_index]
            else:
                error_msg = ""
                log_warning(
                    f"No error message available for failed test: {failed_test_name}"
                )
            error_index += 1

            _process_failed_test(results, failed_test_name, current_suite, error_msg)
            i += 1
            continue

        i += 1
    return results


def _format_suite_details(suite: str, data: Dict[str, Any]) -> str:
    """
    Format test suite details into Markdown.

    Args:
        suite: Suite name
        data: Suite data with passed/failed counts and test details

    Returns:
        Formatted Markdown string for the suite
    """
    suite_status_emoji = "✅" if data["failed"] == 0 else "❌"
    details = f"#### {suite_status_emoji} Suite: `{suite}` ({data['passed']} Passed, {data['failed']} Failed)\n"
    details += "```\n"

    for test in data["tests"]:
        status_char = "✓" if test["status"] == "passed" else "✖"
        details += f"{status_char} {test['name']}\n"
        if test["status"] == "failed" and test.get("error"):
            # Clean up error message (remove redundant "Error:" prefix if it exists)
            error_msg = test["error"]
            if error_msg.startswith("Error: "):
                error_msg = error_msg[7:]  # Remove "Error: " prefix
            details += f"  Error: {error_msg}\n"

    details += "```\n"
    return details


def _get_github_context() -> Dict[str, str]:
    """
    Extract GitHub context from environment variables.

    Returns:
        Dictionary with GitHub context information.
        Missing environment variables default to empty strings for deterministic behavior.
    """
    return {
        "sha": os.environ.get("GITHUB_SHA", ""),
        "ref": os.environ.get("GITHUB_REF", "")
        .replace("refs/heads/", "")
        .replace("refs/pull/", "PR #")
        .replace("/merge", ""),
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "actor": os.environ.get("GITHUB_ACTOR", ""),
        "server_url": os.environ.get("GITHUB_SERVER_URL", "").rstrip(
            "/"
        ),  # GHES compatibility
        "event_name": os.environ.get(
            "WORKFLOW_CONTEXT", os.environ.get("GITHUB_EVENT_NAME", "")
        ),
    }


def _get_workflow_context_display(context: Dict[str, str]) -> str:
    """
    Generate user-friendly display text for workflow context.

    Args:
        context: GitHub context dictionary

    Returns:
        Human-readable workflow context string with emoji
    """
    event_name = context.get("event_name", "")

    context_displays = {
        "pull_request": "🔀 Pull Request",
        "push": "📤 Push",
        "workflow_dispatch": "🚀 Manual Trigger",
        "schedule": "⏰ Scheduled",
        "merge_group": "🔗 Merge Queue",
        "release": "🎉 Release",
    }

    return context_displays.get(
        event_name, f"⚡ {event_name.title() if event_name else 'Workflow'}"
    )


def _determine_command_type(command: str) -> str:
    """Determine command type for display purposes."""
    if command.startswith("test") or command.startswith("run test"):
        return "Test"
    elif command.startswith("collection") or command.startswith("run collection"):
        return "Collection"
    else:
        return command.replace("run ", "").title()


def _build_report_header(
    command_type: str,
    overall_status: str,
    status_emoji: str,
    identifier: str,
    github_context: Dict[str, str],
) -> str:
    """Build the main report header with status and context."""
    report_content = f"## Insomnia {command_type} Results\n\n"

    # Status line with identifier info
    report_content += f"{status_emoji} **Insomnia {command_type} Status: {overall_status}**{f' for `{identifier}`' if identifier else ''}"

    # Add workflow context and actor info
    workflow_display = _get_workflow_context_display(github_context)
    if github_context["actor"]:
        report_content += (
            f" — {workflow_display.lower()} by `{github_context['actor']}`"
        )
    else:
        report_content += f" — {workflow_display.lower()}"

    # Add GitHub Action run link
    if github_context.get("run_id") and github_context.get("repository"):
        run_url = f"https://github.com/{github_context['repository']}/actions/runs/{github_context['run_id']}"
        report_content += f" | [📋 View Action Run]({run_url})"

    report_content += "\n\n"
    return report_content


def _build_summary_table(parsed_results: Dict[str, Any], command_type: str) -> str:
    """Build the summary metrics table."""
    success_rate = (
        round((parsed_results["passed"] / parsed_results["total"]) * 100)
        if parsed_results["total"] > 0
        else 0
    )

    content = "### Summary\n"
    content += "| Metric | Value | Status |\n"
    content += "|--------|-------|--------|\n"
    content += f"| **Total {command_type}s** | {parsed_results['total']} | {'🎯' if parsed_results['total'] > 0 else '⚠️'} |\n"
    content += f"| **Passed** | {parsed_results['passed']} | {'✅' if parsed_results['passed'] > 0 else '⚪'} |\n"
    content += f"| **Failed** | {parsed_results['failed']} | {'❌' if parsed_results['failed'] > 0 else '✅'} |\n"
    success_rate_emoji = _get_success_rate_emoji(success_rate)
    content += f"| **Success Rate** | {success_rate}% | {success_rate_emoji} |\n"
    content += "\n"
    return content


def _build_suite_details_section(parsed_results: Dict[str, Any]) -> str:
    """Build the collapsible suite details section."""
    meaningful_suites = {
        k: v
        for k, v in parsed_results.get("suites", {}).items()
        if not PASSING_FAILING_PATTERN.match(k) and (v["passed"] > 0 or v["failed"] > 0)
    }

    if not meaningful_suites:
        return ""

    content = "<details><summary>Detailed Test Results by Suite 📚</summary>\n\n"
    for suite_name, suite_data in meaningful_suites.items():
        suite_details = _format_suite_details(suite_name, suite_data)
        content += suite_details
    content += "</details>\n\n"
    return content


def _build_failure_details_section(parsed_results: Dict[str, Any]) -> str:
    """Build the failure details section."""
    failures = parsed_results.get("failures", [])
    if not failures:
        return ""

    content = "<details><summary>❌ Failure Details</summary>\n\n"
    for i, failure in enumerate(failures, 1):
        suite_info = (
            f" ({failure.get('suite', 'Unknown Suite')})"
            if failure.get("suite")
            else ""
        )
        content += f"**{i}. {failure.get('name', 'Unknown Test')}{suite_info}**\n"
        if failure.get("error"):
            content += f"```\n{failure['error']}\n```\n\n"
        else:
            content += "No error details available.\n\n"
    content += "</details>\n\n"
    return content


def _build_raw_output_section(raw_output: str) -> str:
    """Build the raw output section."""
    content = "<details><summary>Raw Inso CLI Output 📜</summary>\n\n"
    content += "```\n" + raw_output.strip() + "\n```\n"
    content += "</details>\n"
    return content


def format_markdown_report(
    parsed_results: Dict[str, Any],
    command: str,
    identifier: str,
    exit_code: int,
    raw_output: str,
) -> Tuple[str, str]:
    """
    Format test results into standardized Markdown for GitHub PR comments.

    Args:
        parsed_results: Structured test results from parse_inso_output()
        command: The inso command that was executed
        identifier: Test suite or collection identifier
        exit_code: Process exit code from inso CLI
        raw_output: Raw CLI output for reference

    Returns:
        Tuple of (markdown_report, overall_status)

    Raises:
        ValueError: If required parameters are invalid
    """
    # Input validation
    if not isinstance(parsed_results, dict):
        raise ValueError("parsed_results must be a dictionary")
    if not isinstance(exit_code, int):
        raise ValueError("exit_code must be an integer")

    # Ensure required keys exist with defaults
    parsed_results.setdefault("total", 0)
    parsed_results.setdefault("passed", 0)
    parsed_results.setdefault("failed", 0)
    parsed_results.setdefault("suites", {})
    parsed_results.setdefault("failures", [])

    # Determine overall status
    status_emoji = "✅" if parsed_results["failed"] == 0 and exit_code == 0 else "❌"
    overall_status = (
        "PASSED" if parsed_results["failed"] == 0 and exit_code == 0 else "FAILED"
    )

    # Get GitHub context and determine command type
    github_context = _get_github_context()
    command_type = _determine_command_type(command)

    # Build report sections
    report_content = _build_report_header(
        command_type, overall_status, status_emoji, identifier, github_context
    )
    report_content += _build_summary_table(parsed_results, command_type)
    report_content += _build_suite_details_section(parsed_results)
    report_content += _build_failure_details_section(parsed_results)
    report_content += _build_raw_output_section(raw_output)

    return report_content, overall_status


def main() -> None:
    """
    Main entry point for the Insomnia Action report generator.

    Validates environment, parses CLI output, generates reports, and sets GitHub outputs.
    Designed for enterprise-grade reliability and deterministic behavior.

    Environment Variables Required:
        INSO_RAW_OUTPUT: Raw output from inso CLI
        INSO_EXIT_CODE: Exit code from inso CLI
        INPUT_COMMAND_RAN: Command that was executed
        INPUT_IDENTIFIER_RAN: Identifier used (may be empty)
        GITHUB_OUTPUT: Path to GitHub Actions output file

    Raises:
        SystemExit: On validation errors or processing failures
    """
    log_section("🚦 Insomnia Action Report Generation Start")

    # Validate required environment variables
    required_envs = [
        "INSO_RAW_OUTPUT",
        "INSO_EXIT_CODE",
        "INPUT_COMMAND_RAN",
        "INPUT_IDENTIFIER_RAN",
        "GITHUB_OUTPUT",
    ]
    missing = [env for env in required_envs if not os.environ.get(env)]
    if missing:
        error_exit(f"Missing required environment variables: {', '.join(missing)}")

    # Extract and validate environment variables
    inso_raw_output = os.environ["INSO_RAW_OUTPUT"]
    if not inso_raw_output.strip():
        error_exit("INSO_RAW_OUTPUT must not be empty")

    try:
        inso_exit_code = int(os.environ["INSO_EXIT_CODE"])
    except (ValueError, TypeError):
        error_exit("INSO_EXIT_CODE must be a valid integer.")

    command_ran = os.environ["INPUT_COMMAND_RAN"]
    identifier_ran = os.environ["INPUT_IDENTIFIER_RAN"]
    github_output = os.environ["GITHUB_OUTPUT"]

    # Parse and process results
    log_debug(
        f"Parsing inso output for command: {command_ran}, identifier: {identifier_ran}"
    )
    try:
        parsed_results = parse_inso_output(inso_raw_output)
        comment_body, overall_status = format_markdown_report(
            parsed_results, command_ran, identifier_ran, inso_exit_code, inso_raw_output
        )
    except Exception as e:
        error_exit(f"Failed to process inso output: {str(e)}")

    # Set GitHub Action outputs (deterministic, no file artifacts)
    try:
        with open(github_output, "a", encoding="utf-8") as out:
            out.write(f"summary={overall_status}\n")
            out.write(f"comment_body<<EOF\n{comment_body}\nEOF\n")
    except IOError as e:
        error_exit(f"Failed to write GitHub outputs: {str(e)}")

    log_section("✅ Report generation complete.")


if __name__ == "__main__":
    main()
