import pytest
from insomnia_run.reporter import Reporter
from insomnia_run.models import (
    RunType,
    InsoStatus,
    InsoResult,
    InsoRunReport,
)


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

        # Should not be escaped (it's markdown, not HTML)
        assert "Test with <special> & 'chars'" in markdown

    def test_long_target_name(self, reporter):
        report = InsoRunReport(
            plan_end=0,
            target_name="A" * 100,
        )
        markdown = reporter.generate_markdown(report)

        assert ("A" * 100) in markdown
