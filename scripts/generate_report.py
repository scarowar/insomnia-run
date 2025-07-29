#!/usr/bin/env python3
import os
import re
import sys
from typing import Any, Dict, Tuple, List


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


def _strip_ansi_codes(text: str) -> str:
    """
    Remove ANSI color codes and formatting from text.
    
    Args:
        text: Text potentially containing ANSI codes
        
    Returns:
        Clean text without ANSI codes
    """
    # Remove ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    # Remove bracket codes like [1m, [22m, [31m, [39m
    bracket_codes = re.compile(r'\[[0-9;]*m')
    text = ansi_escape.sub('', text)
    text = bracket_codes.sub('', text)
    return text


def _parse_suite_line(line: str) -> str:
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
    
    # Skip summary lines like "1 passing (264ms)", "Test results:", etc.
    if re.match(r"^\d+\s+(passing|failing)", stripped):
        return None
    if re.match(r"^(Test results?|Tests?:|Test Requests?|Error:|Warning:|Total:|Summary)", stripped, re.IGNORECASE):
        return None
    
    # Skip lines that look like error messages, stack traces, or analysis content
    if stripped.startswith(('Error:', 'at ', 'Expected', 'AssertionError', 'TypeError', 'ReferenceError', 'Total:')):
        return None
        
    # Skip lines that contain analysis keywords
    if re.search(r'\b(Analysis|Summary|Total)\b', stripped, re.IGNORECASE):
        return None
    
    # Only match lines that are indented (typically 2 spaces) but don't start with test status symbols
    suite_regexes = [
        re.compile(r"^\s{2,}(?![\s✓✗✔❌✅✖])(.*)$"),  # Indented, not a status symbol
        re.compile(r"^»\s*(.+?)\.")  # Legacy/alt format
    ]
    
    for regex in suite_regexes:
        match = regex.match(line)
        if match:
            suite_name = match.group(1).strip()
            # Additional filters for non-suite content
            if (not re.match(r"^\d+\s+(passing|failing)", suite_name) and 
                not suite_name.startswith(('Error:', 'Expected', 'at ', 'AssertionError', 'Total:')) and
                not re.search(r'\b(Analysis|Summary|Total)\b', suite_name, re.IGNORECASE) and
                len(suite_name) > 0):
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
    match = re.match(r"^\s*[✓✔✅]\s*(.*?)(?:\s\((\d+)ms\))?$", line)
    return match.group(1).strip() if match else None


def _parse_failed_line(line: str) -> str:
    """
    Extract test name from a failed test line.
    
    Args:
        line: CLI output line potentially containing a failed test
        
    Returns:
        Test name if line represents a failed test, None otherwise
    """
    match = re.match(r"^\s*[✗✖❌]\s*(.*)$", line)
    return match.group(1).strip() if match else None


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
    error_lines = []
    
    # Look ahead for actual error messages, not summary lines
    for j in range(start_idx + 1, len(lines)):
        next_line = lines[j].strip()
        if not next_line:
            continue
            
        # Stop if we hit another test result or suite
        if (re.match(r"^\s*[✓✔✅✗✖❌]", next_line) or 
            re.match(r"^\s{2}[A-Za-z]", next_line)):
            break
            
        # Stop if we hit summary lines (but don't include them)
        if (re.match(r"^\[[0-9;]*m.*\[[0-9;]*m.*total", next_line) or  # ANSI summary lines
            re.match(r"^Test(s)?:\s+", next_line) or
            re.match(r"^Test Requests?:\s+", next_line) or
            re.match(r"^\d+\s+(passing|failing)", next_line)):
            break
            
        # Include actual error lines that start with "error:"
        if next_line.startswith('error:'):
            clean_error = _strip_ansi_codes(next_line)
            # Remove the "error:" prefix and clean up
            clean_error = clean_error.replace('error:', '').strip()
            if clean_error and clean_error not in error_lines:
                error_lines.append(clean_error)
    
    # If no specific errors found, look for them in a different section
    if not error_lines:
        # Look for errors after summary lines
        for j in range(len(lines)):
            line = lines[j].strip()
            if line.startswith('error:'):
                clean_error = _strip_ansi_codes(line)
                clean_error = clean_error.replace('error:', '').strip()
                if clean_error:
                    error_lines.append(clean_error)
    
    error_msg = "\n".join(error_lines).strip()
    return test_name, error_msg

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
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "failures": [],
        "suites": {}
    }
    current_suite = "General"
    lines = output.splitlines()
    
    # First pass: collect all error messages
    all_errors = []
    for line in lines:
        if line.strip().startswith('error:'):
            clean_error = _strip_ansi_codes(line.strip())
            clean_error = clean_error.replace('error:', '').strip()
            if clean_error:
                all_errors.append(clean_error)
    
    error_index = 0
    i = 0
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
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
            test_name = _parse_failed_line(line)
            # Assign the next available error message
            error_msg = all_errors[error_index] if error_index < len(all_errors) else ""
            error_index += 1
            
            results["total"] += 1
            results["failed"] += 1
            if current_suite not in results["suites"]:
                results["suites"][current_suite] = {"passed": 0, "failed": 0, "tests": []}
            results["suites"][current_suite]["failed"] += 1
            failure_details = {"name": test_name, "status": "failed", "suite": current_suite, "error": error_msg}
            results["failures"].append(failure_details)
            results["suites"][current_suite]["tests"].append(failure_details)
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
        "ref": os.environ.get("GITHUB_REF", "").replace("refs/heads/", "").replace("refs/pull/", "PR #").replace("/merge", ""),
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "actor": os.environ.get("GITHUB_ACTOR", ""),
        "server_url": os.environ.get("GITHUB_SERVER_URL", "").rstrip("/"),  # GHES compatibility
        "event_name": os.environ.get("WORKFLOW_CONTEXT", os.environ.get("GITHUB_EVENT_NAME", "")),
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
        "release": "🎉 Release"
    }
    
    return context_displays.get(event_name, f"⚡ {event_name.title() if event_name else 'Workflow'}")

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
    overall_status = "PASSED" if parsed_results["failed"] == 0 and exit_code == 0 else "FAILED"
    
    # Get GitHub context deterministically
    github_context = _get_github_context()
    
    # Extract command type for display
    if command.startswith('test') or command.startswith('run test'):
        command_type = "Test"
    elif command.startswith('collection') or command.startswith('run collection'):
        command_type = "Collection"
    else:
        command_type = command.replace('run ', '').title()
    
    # Build report header with dynamic title
    report_content = f"## Insomnia {command_type} Results\n\n"
    
    # Status line with identifier info
    if identifier:
        report_content += f"{status_emoji} **Insomnia {command_type} Status: {overall_status}** for `{identifier}`"
    else:
        report_content += f"{status_emoji} **Insomnia {command_type} Status: {overall_status}**"
    
    # Add workflow context and actor info
    workflow_display = _get_workflow_context_display(github_context)
    if github_context["actor"]:
        report_content += f" — {workflow_display.lower()} by `{github_context['actor']}`"
    else:
        report_content += f" — {workflow_display.lower()}"
    
    # Add GitHub Action run link
    if github_context.get("run_id") and github_context.get("repository"):
        run_url = f"https://github.com/{github_context['repository']}/actions/runs/{github_context['run_id']}"
        report_content += f" | [📋 View Action Run]({run_url})"
    
    report_content += "\n\n"
    
    # Summary metrics table
    success_rate = round((parsed_results["passed"] / parsed_results["total"]) * 100) if parsed_results["total"] > 0 else 0
    
    report_content += "### Summary\n"
    report_content += "| Metric | Value | Status |\n"
    report_content += "|--------|-------|--------|\n"
    report_content += f"| **Total {command_type}s** | {parsed_results['total']} | {'🎯' if parsed_results['total'] > 0 else '⚠️'} |\n"
    report_content += f"| **Passed** | {parsed_results['passed']} | {'✅' if parsed_results['passed'] > 0 else '⚪'} |\n"
    report_content += f"| **Failed** | {parsed_results['failed']} | {'❌' if parsed_results['failed'] > 0 else '✅'} |\n"
    report_content += f"| **Success Rate** | {success_rate}% | {'🏆' if success_rate == 100 else '📈' if success_rate >= 80 else '⚠️' if success_rate >= 70 else '💥'} |\n"
    
    report_content += "\n"
    
    # Suite details in collapsible section
    meaningful_suites = {k: v for k, v in parsed_results.get("suites", {}).items() 
                        if not re.match(r"^\d+\s+(passing|failing)", k) and (v["passed"] > 0 or v["failed"] > 0)}
    
    if meaningful_suites:
        report_content += "<details><summary>Detailed Test Results by Suite 📚</summary>\n\n"
        
        for suite_name, suite_data in meaningful_suites.items():
            suite_details = _format_suite_details(suite_name, suite_data)
            report_content += suite_details
        
        report_content += "</details>\n\n"
    
    # Failure details section
    if parsed_results.get("failures") and len(parsed_results["failures"]) > 0:
        report_content += "<details><summary>❌ Failure Details</summary>\n\n"
        for i, failure in enumerate(parsed_results["failures"], 1):
            suite_info = f" ({failure.get('suite', 'Unknown Suite')})" if failure.get('suite') else ""
            report_content += f"**{i}. {failure.get('name', 'Unknown Test')}{suite_info}**\n"
            if failure.get('error'):
                report_content += f"```\n{failure['error']}\n```\n\n"
            else:
                report_content += "No error details available.\n\n"
        report_content += "</details>\n\n"
    
    # Raw output section
    report_content += "<details><summary>Raw Inso CLI Output 📜</summary>\n\n"
    report_content += "```\n" + raw_output.strip() + "\n```\n"
    report_content += "</details>\n"
    
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
        "INSO_RAW_OUTPUT", "INSO_EXIT_CODE", "INPUT_COMMAND_RAN", 
        "INPUT_IDENTIFIER_RAN", "GITHUB_OUTPUT"
    ]
    missing = [env for env in required_envs if not os.environ.get(env)]
    if missing:
        error_exit(f"Missing required environment variables: {', '.join(missing)}")

    # Extract and validate environment variables
    inso_raw_output = os.environ["INSO_RAW_OUTPUT"]
    try:
        inso_exit_code = int(os.environ["INSO_EXIT_CODE"])
    except (ValueError, TypeError):
        error_exit("INSO_EXIT_CODE must be a valid integer.")

    command_ran = os.environ["INPUT_COMMAND_RAN"]
    identifier_ran = os.environ["INPUT_IDENTIFIER_RAN"]
    github_output = os.environ["GITHUB_OUTPUT"]

    # Parse and process results
    log_debug(f"Parsing inso output for command: {command_ran}, identifier: {identifier_ran}")
    try:
        parsed_results = parse_inso_output(inso_raw_output)
        comment_body, overall_status = format_markdown_report(
            parsed_results, command_ran, identifier_ran, inso_exit_code, inso_raw_output
        )
    except Exception as e:
        error_exit(f"Failed to process inso output: {str(e)}")

    # Set GitHub Action outputs (deterministic, no file artifacts)
    try:
        with open(github_output, 'a', encoding='utf-8') as out:
            out.write(f"summary={overall_status}\n")
            out.write(f"comment_body<<EOF\n{comment_body}\nEOF\n")
    except IOError as e:
        error_exit(f"Failed to write GitHub outputs: {str(e)}")

    log_section("✅ Report generation complete.")


if __name__ == "__main__":
    main()