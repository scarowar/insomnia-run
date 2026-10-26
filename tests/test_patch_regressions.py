"""Regression coverage for report completeness, credential handling, and outcomes."""

import json
import sys
from urllib.parse import urlencode
from xml.etree import ElementTree

from markdown_it import MarkdownIt
from pydantic import BaseModel
import pytest

from insomnia_run.action_runtime import run_action
from insomnia_run.models import InsoResult, InsoRunReport, RequestExecution
from insomnia_run.parser import TapParser
from insomnia_run.privacy import Redactor
from insomnia_run.publication import failure_annotations
from insomnia_run.reporter import Reporter
from insomnia_run.runner import InsoRunner


@pytest.mark.parametrize("value", ["short&tail+123", "a+b", "value=a&b=c", "秘密&tail"])
def test_literal_and_decoded_override_values_are_both_private(value):
    for entry in [f"PASSWORD={value}", urlencode({"PASSWORD": value})]:
        redactor = Redactor(env_vars=[entry])
        assert redactor.redact(value) == "[REDACTED]"


def test_dynamic_dictionary_keys_are_private_without_losing_collisions():
    class Payload(BaseModel):
        data: dict[str, str]

    payload = Payload(
        data={"left-value": "one", "right-value": "two", "my_api_key": "short"}
    )
    redacted = Redactor(["left-value", "right-value"]).redact_report(payload)
    assert "left-value" not in redacted.model_dump_json()
    assert "right-value" not in redacted.model_dump_json()
    assert redacted.data["my_api_key"] == "[REDACTED]"
    assert len(redacted.data) == 3
    assert {"one", "two"} <= set(redacted.data.values())


def test_real_child_filters_credentials_but_preserves_runtime_configuration(
    monkeypatch,
):
    private = [
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AZURE_CLIENT_SECRET",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "NPM_TOKEN",
        "ACTIONS_RUNTIME_TOKEN",
        "GITHUB_APP_TOKEN",
        "GITHUB_ENV",
        "GITHUB_PATH",
        "GITHUB_OUTPUT",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_STATE",
        "STATE_SAVED_TOKEN",
        "API_BASE_URL",
    ]
    safe = {
        "HTTPS_PROXY": "http://proxy.test:8080",
        "SSL_CERT_FILE": "/tmp/ca.pem",
        "GITHUB_WORKSPACE": "/tmp/collection-workspace",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REF": "refs/heads/main",
        "LC_ALL": "C",
    }
    for key in private:
        monkeypatch.setenv(key, "synthetic-sentinel")
    for key, value in safe.items():
        monkeypatch.setenv(key, value)
    script = "import json,os; print(json.dumps(dict(os.environ)))"
    result = InsoRunner._run_command([sys.executable, "-c", script], 10)
    assert result.returncode == 0
    child = json.loads(result.stdout)
    assert not set(private) & child.keys()
    assert all(child[key] == value for key, value in safe.items())
    assert child["INSO_TELEMETRY_DISABLED"] == "1"


def grouped_report(counts=(29, 10, 21, 1, 1), *, failed=True, message=None):
    results = []
    for execution, count in enumerate(counts, 1):
        for index in range(count):
            results.append(
                InsoResult(
                    id=len(results) + 1,
                    execution_id=execution,
                    status="FAIL"
                    if failed and execution == 1 and index < 2
                    else "PASS",
                    description=f"check-{execution}-{index}",
                    message=message,
                )
            )
    return InsoRunReport(
        source="native",
        plan_end=len(results),
        executions=[
            RequestExecution(id=i, name=f"POST /request-{i}")
            for i in range(1, len(counts) + 1)
        ],
        results=results,
    )


@pytest.mark.parametrize("failed", [True, False])
def test_sixty_two_assertions_do_not_hide_requests_that_fit(failed):
    report = grouped_report(failed=failed)
    markdown = Reporter().generate_markdown(report)
    assert all(f"POST /request-{i}" in markdown for i in range(1, 6))
    assert "check-3-20" in markdown
    assert "more results omitted" not in markdown
    dom = ElementTree.fromstring(
        f"<div>{MarkdownIt().enable('table').render(markdown)}</div>"
    )
    overview = next(
        table
        for table in dom.findall(".//table")
        if [cell.text for cell in table.findall("./thead/tr/th")]
        == ["Request", "Passed", "Failed", "Skipped", "Response"]
    )
    counts = [
        [cell.text for cell in row.findall("td")[1:4]]
        for row in overview.findall("./tbody/tr")
    ]
    assert counts == [
        ["27", "2", "0"] if failed else ["29", "0", "0"],
        ["10", "0", "0"],
        ["21", "0", "0"],
        ["1", "0", "0"],
        ["1", "0", "0"],
    ]
    assert len(markdown.encode()) <= 60_000


def test_large_failure_reasons_cannot_hide_later_failure_descriptions():
    report = grouped_report((2, 1), message="<&>" * 5000)
    report.results[-1].status = "FAIL"
    markdown = Reporter().generate_markdown(report, max_bytes=4000)
    assert all(result.description in markdown for result in report.results)
    assert "omitted" in markdown or "truncated" in markdown
    assert len(markdown.encode()) <= 4000


def test_large_group_lists_and_unicode_respect_final_budget():
    report = grouped_report((0,) * 400, failed=False)
    for execution in report.executions:
        execution.name = "<>&秘密" * 100
    markdown = Reporter().generate_markdown(report, max_bytes=3000)
    assert len(markdown.encode()) <= 3000
    assert "request groups omitted" in markdown
    assert markdown.count("<details>") == markdown.count("</details>")
    assert "| 400 | 0 | 0 | 0 | 0 |" in markdown


@pytest.mark.parametrize("failed", [False, True])
def test_incomplete_outcomes_agree_with_junit_without_breaking_assertion_bail(failed):
    report = InsoRunReport(
        plan_end=1,
        complete=False,
        results=[
            InsoResult(id=1, status="FAIL" if failed else "PASS", description="partial")
        ],
    )
    assert report.exit_code == (1 if failed else 3)
    suite = ElementTree.fromstring(Reporter().generate_junit(report))
    assert int(suite.get("errors")) == (0 if failed else 1)
    assert len(suite.findall("testcase")) == int(suite.get("tests"))


def test_junit_summary_is_short_but_evidence_is_complete():
    message = "first line\n" + "full evidence\n" * 1000
    report = InsoRunReport(
        plan_end=1,
        results=[InsoResult(id=1, status="FAIL", description="check", message=message)],
    )
    failure = ElementTree.fromstring(Reporter().generate_junit(report)).find(
        "./testcase/failure"
    )
    assert failure.get("message") == "first line"
    assert failure.text == message
    assert (
        "time"
        not in ElementTree.fromstring(
            Reporter().generate_junit(InsoRunReport(plan_end=0))
        ).attrib
    )


@pytest.mark.parametrize("ending", ["", "\n", "\nnext diagnostic"])
def test_interrupted_tap_yaml_preserves_failure_evidence(ending):
    report = TapParser().parse(
        "TAP version 13\n1..1\nnot ok 1 failed\n  ---\n  message: partial reason"
        + ending,
        require_tap=True,
    )
    assert "partial reason" in report.results[0].message


def test_annotations_fit_the_budget_after_percent_escaping():
    (annotation,) = failure_annotations(["%\r\n秘密" * 1000])
    assert len(annotation.encode()) <= 2000
    assert annotation.startswith("::error title=Insomnia Run::")
    assert "\n" not in annotation
    assert "\r" not in annotation
    assert not annotation.endswith(("%", "%2", "%0"))


def test_annotation_invalid_unicode_is_safe_to_publish():
    (annotation,) = failure_annotations(["invalid\ud800text"])
    assert "\ufffd" in annotation
    assert len(annotation.encode("utf-8")) <= 2000


def test_missing_runner_temp_is_a_configuration_error(capsys):
    assert run_action({}) == 2
    assert "RUNNER_TEMP" in capsys.readouterr().out


def test_invalid_options_do_not_leave_report_directories(tmp_path):
    assert run_action({"RUNNER_TEMP": str(tmp_path), "REQUEST_TIMEOUT": "invalid"}) == 2
    assert not list(tmp_path.glob("insomnia-run-reports.*"))


@pytest.mark.parametrize("missing", ["GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"])
def test_missing_publication_paths_fail_before_execution(
    tmp_path, monkeypatch, capsys, missing
):
    from insomnia_run import action_runtime

    env = {
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
    }
    del env[missing]
    monkeypatch.setattr(
        action_runtime,
        "_run_reports",
        lambda *args: pytest.fail("Execution must not begin without publication paths"),
    )
    assert run_action(env) == 2
    assert missing in capsys.readouterr().out
    assert not list(tmp_path.glob("insomnia-run-reports.*"))


def test_complete_collection_tap_explains_limited_evidence():
    report = InsoRunReport(
        plan_end=1,
        results=[
            InsoResult(
                id=1, status="PASS", description="check", duration_seconds=0.0001
            )
        ],
    )
    markdown = Reporter().generate_markdown(report)
    assert "Request details unavailable" in markdown
    assert "<1 ms" in "".join(
        ElementTree.fromstring(
            "<div>" + MarkdownIt().render(markdown) + "</div>"
        ).itertext()
    )


def test_action_summary_uses_its_own_remaining_budget(tmp_path, monkeypatch):
    from insomnia_run import action_runtime

    report = grouped_report((1,) * 600, failed=False)
    for execution in report.executions:
        execution.name += " long name" * 10

    def reports(env, directory, options):
        (directory / "report.json").write_text(report.model_dump_json())
        (directory / "report.md").write_text(Reporter().generate_markdown(report))
        (directory / "junit.xml").write_text(Reporter().generate_junit(report))
        return 0

    monkeypatch.setattr(action_runtime, "_run_reports", reports)
    summary = tmp_path / "summary"
    assert (
        run_action(
            {
                "RUNNER_TEMP": str(tmp_path),
                "GITHUB_OUTPUT": str(tmp_path / "outputs"),
                "GITHUB_STEP_SUMMARY": str(summary),
            }
        )
        == 0
    )
    content = summary.read_text()
    assert "POST /request-600" in content
    assert "request groups omitted" not in content
    assert len(summary.read_bytes()) <= 1024 * 1024
    (directory,) = tmp_path.glob("insomnia-run-reports.*")
    assert len((directory / "report.md").read_bytes()) <= 60_000
    assert "request groups omitted" in (directory / "report.md").read_text()
    summary.write_text("x" * (1024 * 1024 - 100))
    assert (
        run_action(
            {
                "RUNNER_TEMP": str(tmp_path),
                "GITHUB_OUTPUT": str(tmp_path / "outputs"),
                "GITHUB_STEP_SUMMARY": str(summary),
            }
        )
        == 0
    )
    assert len(summary.read_bytes()) <= 1024 * 1024


def test_native_message_cleanup_preserves_canonical_evidence():
    raw = "error: Error: mismatch\n1. missing item | ACTUAL: 1 | EXPECTED: 0"
    report = InsoRunReport(
        plan_end=1,
        source="native",
        results=[
            InsoResult(id=1, status="FAIL", description="difference", message=raw)
        ],
    )
    markdown = Reporter().generate_markdown(report)
    assert "error: Error:" not in markdown
    assert "missing item\nActual: 1\nExpected: 0" in markdown
    assert report.results[0].message == raw
    assert (
        ElementTree.fromstring(Reporter().generate_junit(report))
        .find("./testcase/failure")
        .text
        == raw
    )
