import pytest
from xml.etree import ElementTree

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

    def test_raw_output_is_hidden_by_default(self, reporter):
        report = InsoRunReport(
            plan_end=1,
            results=[InsoResult(id=1, status=InsoStatus.PASS, description="Test")],
            raw_output="ok 1 - Test\n# tests 1\n",
        )
        markdown = reporter.generate_markdown(report)

        assert "<details>" not in markdown
        assert "ok 1 - Test" not in markdown

    def test_raw_output_can_be_included(self, reporter):
        report = InsoRunReport(
            plan_end=1,
            results=[InsoResult(id=1, status=InsoStatus.PASS, description="Test")],
            raw_output="ok 1 - Test\n# tests 1\n",
        )
        markdown = reporter.generate_markdown(report, include_raw_output=True)

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


class TestReporterJUnitGeneration:
    @pytest.fixture
    def reporter(self):
        return Reporter()

    def parse_junit(self, xml: str):
        return ElementTree.fromstring(xml)

    def test_passing_collection_junit(self, reporter):
        report = InsoRunReport(
            run_type=RunType.COLLECTION,
            target_name="My Collection",
            plan_end=2,
            results=[
                InsoResult(id=1, status=InsoStatus.PASS, description="GET users"),
                InsoResult(id=2, status=InsoStatus.PASS, description="POST login"),
            ],
        )

        suite = self.parse_junit(reporter.generate_junit(report))

        assert suite.tag == "testsuite"
        assert suite.attrib["name"] == "Insomnia Collection"
        assert suite.attrib["tests"] == "2"
        assert suite.attrib["failures"] == "0"
        assert suite.attrib["errors"] == "0"
        assert suite.attrib["skipped"] == "0"
        assert [case.attrib["name"] for case in suite.findall("testcase")] == [
            "GET users",
            "POST login",
        ]

    def test_failing_and_skipped_results_junit(self, reporter):
        report = InsoRunReport(
            run_type=RunType.TEST,
            target_name="Auth Tests",
            plan_end=3,
            results=[
                InsoResult(id=1, status=InsoStatus.PASS, description="passes"),
                InsoResult(id=2, status=InsoStatus.FAIL, description="fails"),
                InsoResult(id=3, status=InsoStatus.SKIP, description="skips"),
            ],
        )

        suite = self.parse_junit(reporter.generate_junit(report))
        cases = suite.findall("testcase")

        assert suite.attrib["name"] == "Insomnia Test Suite"
        assert suite.attrib["tests"] == "3"
        assert suite.attrib["failures"] == "1"
        assert suite.attrib["skipped"] == "1"
        assert cases[1].find("failure").attrib["message"] == "fails"
        assert cases[1].find("failure").text == "Inso reported this test as failed."
        assert cases[2].find("skipped") is not None

    def test_junit_escapes_xml_and_omits_raw_output(self, reporter):
        report = InsoRunReport(
            run_type=RunType.COLLECTION,
            target_name="API <Suite>",
            plan_end=1,
            raw_output="secret-like raw output",
            results=[
                InsoResult(
                    id=1,
                    status=InsoStatus.FAIL,
                    description="GET <users> & 'admins'",
                )
            ],
        )

        xml = reporter.generate_junit(report)
        suite = self.parse_junit(xml)
        testcase = suite.find("testcase")

        assert testcase.attrib["classname"] == "API <Suite>"
        assert testcase.attrib["name"] == "GET <users> & 'admins'"
        assert "secret-like raw output" not in xml

    def test_empty_report_junit(self, reporter):
        suite = self.parse_junit(Reporter().generate_junit(InsoRunReport(plan_end=0)))

        assert suite.attrib["tests"] == "0"
        assert suite.findall("testcase") == []
