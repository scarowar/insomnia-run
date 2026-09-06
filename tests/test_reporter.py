import pytest

from insomnia_run.models import (
    InsoResult,
    InsoRunReport,
    InsoStatus,
    RunType,
)
from insomnia_run.reporter import Reporter


class TestReporterMarkdownGeneration:
    @pytest.fixture
    def reporter(self):
        return Reporter()

    def test_passing_collection_report(self, reporter):
        report = InsoRunReport(
            run_type=RunType.COLLECTION,
            target_name="My Collection",
            plan_end=2,
            results=[
                InsoResult(id=1, status=InsoStatus.PASS, description="Test 1"),
                InsoResult(id=2, status=InsoStatus.PASS, description="Test 2"),
            ],
        )
        markdown = reporter.generate_markdown(report)

        assert "## ✅ Insomnia Collection Passed: My Collection" in markdown
        assert "**2 requests executed** (all passed)" in markdown
        assert "- ✅ **Test 1**" in markdown
        assert "- ✅ **Test 2**" in markdown

    def test_failing_collection_report(self, reporter):
        report = InsoRunReport(
            run_type=RunType.COLLECTION,
            target_name="My Collection",
            plan_end=2,
            results=[
                InsoResult(id=1, status=InsoStatus.PASS, description="Test 1"),
                InsoResult(id=2, status=InsoStatus.FAIL, description="Test 2"),
            ],
        )
        markdown = reporter.generate_markdown(report)

        assert "## ❌ Insomnia Collection Failed: My Collection" in markdown
        assert "(1 passed, 1 failed)" in markdown
        assert "- ✅ **Test 1**" in markdown
        assert "- ❌ **Test 2**" in markdown

    def test_test_suite_report(self, reporter):
        report = InsoRunReport(
            run_type=RunType.TEST,
            target_name="My Test Suite",
            plan_end=1,
            results=[
                InsoResult(id=1, status=InsoStatus.PASS, description="Unit Test"),
            ],
        )
        markdown = reporter.generate_markdown(report)

        assert "## ✅ Insomnia Test Suite Passed: My Test Suite" in markdown

    def test_workflow_url_link(self, reporter):
        report = InsoRunReport(plan_end=0)
        markdown = reporter.generate_markdown(
            report, workflow_url="https://github.com/org/repo/actions/runs/123"
        )

        assert "[workflow logs]" in markdown
        assert "https://github.com/org/repo/actions/runs/123" in markdown

    def test_no_workflow_url(self, reporter):
        report = InsoRunReport(plan_end=0)
        markdown = reporter.generate_markdown(report)

        assert "Check the workflow logs for details" in markdown
        assert "[workflow logs]" not in markdown

    def test_raw_output_in_details(self, reporter):
        report = InsoRunReport(
            plan_end=1,
            results=[InsoResult(id=1, status=InsoStatus.PASS, description="Test")],
            raw_output="ok 1 - Test\n# tests 1\n",
        )
        markdown = reporter.generate_markdown(report)

        assert "<details>" in markdown
        assert "<summary>View raw output</summary>" in markdown
        assert "ok 1 - Test" in markdown

    def test_no_raw_output(self, reporter):
        report = InsoRunReport(plan_end=0)
        markdown = reporter.generate_markdown(report)

        assert "<details>" not in markdown

    def test_target_name_in_summary(self, reporter):
        report = InsoRunReport(plan_end=0, target_name="API Collection")
        markdown = reporter.generate_markdown(report)

        assert "**Target:** `API Collection`" in markdown

    def test_empty_results(self, reporter):
        report = InsoRunReport(plan_end=0)
        markdown = reporter.generate_markdown(report)

        assert "**0 requests executed**" in markdown
        assert "### Test Results" in markdown


class TestReporterEdgeCases:
    @pytest.fixture
    def reporter(self):
        return Reporter()

    def test_special_characters_in_description(self, reporter):
        report = InsoRunReport(
            plan_end=1,
            results=[
                InsoResult(
                    id=1,
                    status=InsoStatus.PASS,
                    description="Test with <special> & 'chars'",
                )
            ],
        )
        markdown = reporter.generate_markdown(report)

        # HTML-escaped (safe in PR comments/step summaries); renders identically
        assert "Test with &lt;special&gt; &amp; 'chars'" in markdown

    def test_long_target_name(self, reporter):
        report = InsoRunReport(
            plan_end=0,
            target_name="A" * 100,
        )
        markdown = reporter.generate_markdown(report)

        assert ("A" * 100) in markdown


# --- Tickets 13/14: escaping, truncation, raw-output gate, JUnit, annotations ---


def _report(results, **kw):
    return InsoRunReport(plan_end=len(results), results=results, **kw)


class TestMarkdownEscaping:
    def test_description_backticks_cannot_break_the_raw_output_fence(self):
        report = _report([InsoResult(id=1, status=InsoStatus.FAIL, description="boom")])
        report.raw_output = "output containing ``` triple backticks"
        markdown = Reporter().generate_markdown(report)
        fence = "````"
        assert fence in markdown
        closing = markdown.rstrip().splitlines()[-2]
        assert closing == fence

    def test_description_html_is_escaped(self):
        report = _report(
            [
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="<script>alert(1)</script>",
                )
            ]
        )
        markdown = Reporter().generate_markdown(report)
        assert "<script>" not in markdown
        assert "&lt;script&gt;" in markdown

    def test_target_name_html_is_escaped(self):
        report = _report([], target_name="<b>bold</b>")
        markdown = Reporter().generate_markdown(report)
        assert "<b>" not in markdown

    def test_workflow_url_renders_as_angle_bracket_destination(self):
        report = _report([])
        markdown = Reporter().generate_markdown(report, workflow_url="https://example.com/run(1)")
        assert "](<https://example.com/run(1)>)" in markdown

    def test_failure_message_rendered_under_failing_bullet(self):
        report = _report(
            [
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="GET /x",
                    message="expected 200, got 500",
                )
            ]
        )
        markdown = Reporter().generate_markdown(report)
        assert "expected 200, got 500" in markdown

    def test_diagnostics_section_rendered(self):
        report = _report([], diagnostics=["Inso exited with code 1: crashed"])
        markdown = Reporter().generate_markdown(report)
        assert "Inso exited with code 1: crashed" in markdown

    def test_test_runs_label_says_tests(self):
        report = _report(
            [InsoResult(id=1, status=InsoStatus.PASS, description="t")],
            run_type=RunType.TEST,
        )
        markdown = Reporter().generate_markdown(report)
        assert "tests executed" in markdown
        assert "requests executed" not in markdown


class TestRawOutputTruncation:
    def test_raw_output_truncated_to_budget(self):
        report = _report([])
        report.raw_output = "x" * 20_000
        markdown = Reporter().generate_markdown(report, raw_output_max_bytes=8192)
        assert len(markdown) < 10_000
        assert "truncated" in markdown

    def test_include_raw_output_false_drops_section(self):
        report = _report([])
        report.raw_output = "x" * 100
        markdown = Reporter().generate_markdown(report, include_raw_output=False)
        assert "View raw output" not in markdown


class TestJunit:
    def test_junit_structure_and_counts(self):
        report = _report(
            [
                InsoResult(id=1, status=InsoStatus.PASS, description="ok one"),
                InsoResult(
                    id=2,
                    status=InsoStatus.FAIL,
                    description="bad two",
                    message="expected 200, got 500",
                ),
                InsoResult(id=3, status=InsoStatus.SKIP, description="skipped three"),
            ],
            target_name="My Suite",
        )
        xml = Reporter().generate_junit(report)

        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        assert 'name="Insomnia Collection"' in xml
        assert 'tests="3"' in xml and 'failures="1"' in xml and 'skipped="1"' in xml
        assert "<failure" in xml and "expected 200, got 500" in xml
        assert "<skipped />" in xml
        assert xml.endswith("</testsuite>\n")

    def test_junit_escapes_xml_specials(self):
        report = _report(
            [InsoResult(id=1, status=InsoStatus.FAIL, description='GET <users> & "admins"')]
        )
        xml = Reporter().generate_junit(report)
        assert "<users>" not in xml
        assert "&lt;users&gt;" in xml

    def test_junit_failure_body_uses_message(self):
        report = _report(
            [
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="d",
                    message="the real reason",
                )
            ]
        )
        xml = Reporter().generate_junit(report)
        assert "the real reason" in xml
        assert "Inso reported this test as failed." not in xml

    def test_junit_failure_body_falls_back_without_message(self):
        report = _report([InsoResult(id=1, status=InsoStatus.FAIL, description="d")])
        xml = Reporter().generate_junit(report)
        assert "<failure " in xml
        assert ">d</failure>" in xml


class TestAnnotations:
    def test_annotations_one_per_failure_capped_at_ten(self):
        results = [
            InsoResult(id=i, status=InsoStatus.FAIL, description=f"f{i}") for i in range(1, 16)
        ]
        lines = Reporter().annotations(_report(results))

        assert len(lines) == 10
        assert all(line.startswith("::error") for line in lines)

    def test_annotation_includes_message(self):
        report = _report(
            [InsoResult(id=1, status=InsoStatus.FAIL, description="GET /x", message="boom")]
        )
        lines = Reporter().annotations(report)
        assert lines == ["::error title=GET /x::boom"]

    def test_annotation_escapes_workflow_command_specials(self):
        report = _report(
            [
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="multi\nline",
                    message="50% of\r\nrequests failed",
                )
            ]
        )
        lines = Reporter().annotations(report)
        assert lines == ["::error title=multi%0Aline::50%25 of%0D%0Arequests failed"]

    def test_no_annotations_without_failures(self):
        report = _report([InsoResult(id=1, status=InsoStatus.PASS, description="fine")])
        assert Reporter().annotations(report) == []


def test_raw_output_fence_is_always_valid_markdown():
    report = InsoRunReport(plan_end=0, raw_output="no backticks in sight")
    markdown = Reporter().generate_markdown(report)
    assert "\n```\n" in markdown
    assert (
        markdown.rstrip().endswith(
            "```</details>".replace("</details>", "").strip() + "\n</details>"
        )
        or "\n```\n</details>" in markdown
    )


class TestReporterContract:
    def test_markdown_escapes_backticks_and_link_brackets(self):
        report = InsoRunReport(
            plan_end=1,
            results=[
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="[click here](https://evil.example) `code`",
                    message="expected `200` [reset](https://x.example)",
                )
            ],
        )
        markdown = Reporter().generate_markdown(report)
        # brackets are escaped so the markdown never renders as a link
        assert "[click here]" not in markdown
        assert "\\[click here\\](https://evil.example)" in markdown
        assert "\\`code\\`" in markdown
        assert "\\`200\\`" in markdown

    def test_junit_strips_xml_invalid_control_characters(self):
        import xml.etree.ElementTree as ET

        report = InsoRunReport(
            plan_end=1,
            results=[InsoResult(id=1, status=InsoStatus.FAIL, description="bad\x0cchar\x07here")],
        )
        xml = Reporter().generate_junit(report)
        ET.fromstring(xml)  # must be well-formed

    def test_headline_warns_when_inso_failed_after_all_tests_passed(self):
        report = InsoRunReport(
            plan_end=1,
            results=[InsoResult(id=1, status=InsoStatus.PASS, description="fine")],
            diagnostics=["Inso exited with code 1: late crash"],
        )
        markdown = Reporter().generate_markdown(report)
        assert "Passed with warnings" in markdown
        assert "## ✅" not in markdown

    def test_results_rendering_capped_at_fifty(self):
        results = [
            InsoResult(id=i, status=InsoStatus.PASS, description=f"t{i}") for i in range(120)
        ]
        markdown = Reporter().generate_markdown(InsoRunReport(plan_end=120, results=results))
        assert "and 70 more results" in markdown
        assert "t60" not in markdown

    def test_annotation_payloads_escaped(self):
        report = InsoRunReport(
            plan_end=1,
            results=[
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="evil%0A%0Dcontent",
                    message="line1%0Aline2",
                )
            ],
        )
        lines = Reporter().annotations(report)
        assert len(lines) == 1
        # % is escaped so a literal %0A cannot become a newline; no real newline
        assert "%250A" in lines[0]
        assert "\n" not in lines[0]
