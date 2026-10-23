import pytest
from markdown_it import MarkdownIt
from xml.etree import ElementTree

from insomnia_run.reporter import Reporter
from insomnia_run.models import (
    RunType,
    InsoStatus,
    InsoResult,
    InsoRunReport,
    RequestExecution,
    RunError,
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

        assert "## ✅ Insomnia Collection Passed: ` My Collection `" in markdown
        assert "**2 test results** (all passed)" in markdown
        assert "- ✅ **` Test 1 `**" in markdown
        assert "- ✅ **` Test 2 `**" in markdown

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

        assert "## ❌ Insomnia Collection Failed: ` My Collection `" in markdown
        assert "(1 passed, 1 failed)" in markdown
        assert "- ✅ **` Test 1 `**" in markdown
        assert "- ❌ **` Test 2 `**" in markdown

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

        assert "## ✅ Insomnia Test Suite Passed: ` My Test Suite `" in markdown

    def test_workflow_url_link(self, reporter):
        report = InsoRunReport(plan_end=0)
        markdown = reporter.generate_markdown(
            report, workflow_url="https://github.com/org/repo/actions/runs/123"
        )

        assert "[workflow run]" in markdown
        assert "https://github.com/org/repo/actions/runs/123" in markdown

    def test_no_workflow_url(self, reporter):
        report = InsoRunReport(plan_end=0)
        markdown = reporter.generate_markdown(report)

        assert "See the workflow run for execution details." in markdown
        assert "[workflow run]" not in markdown

    def test_raw_output_is_hidden_by_default(self, reporter):
        report = InsoRunReport(
            plan_end=1,
            results=[InsoResult(id=1, status=InsoStatus.PASS, description="Test")],
            raw_output="ok 1 - Test\n# tests 1\n",
        )
        markdown = reporter.generate_markdown(report)

        assert "<details>" not in markdown
        assert "ok 1 - Test" not in markdown
        assert "diagnostics are omitted" in markdown
        assert "`--include-raw-output`" in markdown
        assert "contain secrets" in markdown

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
        assert "diagnostics are omitted" not in markdown

    def test_no_raw_output(self, reporter):
        report = InsoRunReport(plan_end=0)
        markdown = reporter.generate_markdown(report)

        assert "<details>" not in markdown

    def test_target_name_in_summary(self, reporter):
        report = InsoRunReport(plan_end=0, target_name="API Collection")
        markdown = reporter.generate_markdown(report)

        assert "**Target:** ` API Collection `" in markdown

    def test_empty_results(self, reporter):
        report = InsoRunReport(plan_end=0)
        markdown = reporter.generate_markdown(report)

        assert "**0 test results**" in markdown
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

        dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")
        assert dom.find(".//li/strong/code").text == "Test with <special> & 'chars'"

    def test_long_target_name(self, reporter):
        report = InsoRunReport(
            plan_end=0,
            target_name="A" * 100,
        )
        markdown = reporter.generate_markdown(report)

        assert ("A" * 100) in markdown


def test_empty_report_does_not_claim_assertions_passed():
    markdown = Reporter().generate_markdown(InsoRunReport(plan_end=0))

    assert "No assertions executed" in markdown
    assert "Passed" not in markdown
    assert "all passed" not in markdown


def test_all_skipped_report_is_not_labelled_passed():
    report = InsoRunReport(
        plan_end=1,
        results=[
            InsoResult(id=1, status=InsoStatus.SKIP, description="not applicable")
        ],
    )

    markdown = Reporter().generate_markdown(report)

    assert "Skipped" in markdown
    assert "Passed" not in markdown


def test_summary_counts_results_without_claiming_request_execution():
    report = InsoRunReport(
        plan_end=2,
        results=[
            InsoResult(id=1, status=InsoStatus.PASS, description="status assertion"),
            InsoResult(id=2, status=InsoStatus.PASS, description="body assertion"),
        ],
    )

    markdown = Reporter().generate_markdown(report)

    assert "2 test results" in markdown
    assert "requests executed" not in markdown


@pytest.mark.parametrize(
    "description",
    [
        "[click](https://example.invalid) ![image](https://example.invalid/x)",
        "**forged** _emphasis_ `code` \\*escaped* | column |",
        "<img src=x onerror=alert(1)> &lt;script&gt; & text",
        "test\r\n\n# forged heading\n\n- forged result\tend",
        "@ghost #131 www.example.invalid",
        "`",
        "``two``",
        "`edges` and `` mixed ` delimiters ``",
        "ends with \\",
    ],
)
def test_result_descriptions_render_as_literal_inline_text(description):
    report = InsoRunReport(
        plan_end=1,
        target_name=description,
        results=[InsoResult(id=1, status=InsoStatus.FAIL, description=description)],
    )

    markdown = Reporter().generate_markdown(report)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")

    expected = " ".join(description.split())
    assert dom.find(".//li/strong/code").text == expected
    assert dom.find("./h2/code").text == expected
    assert dom.find("./ul/li/code").text == expected
    assert dom.findall(".//a") == dom.findall(".//img") == []
    assert dom.findall(".//h1") == []


@pytest.mark.parametrize(
    "target_name",
    [
        "<b>suite</b>\n\n# [forged](https://example.invalid)",
        "Suite ###",
        "@ghost #131 www.example.invalid",
        "`Suite`",
    ],
)
def test_target_name_renders_as_literal_inline_text(target_name):
    report = InsoRunReport(plan_end=0, target_name=target_name)

    markdown = Reporter().generate_markdown(report)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")

    expected = " ".join(target_name.split())
    assert dom.find("./h2/code").text == expected
    assert dom.find("./ul/li/code").text == expected
    assert dom.findall(".//a") == dom.findall(".//b") == []


@pytest.mark.parametrize("run_length", [79, 80, 81, 160])
def test_long_backtick_names_use_short_gfm_code_delimiters(run_length):
    name = "`" * run_length + " @ghost #131 ![x](https://example.invalid/x)"
    report = InsoRunReport(
        plan_end=1,
        target_name=name,
        results=[InsoResult(id=1, status=InsoStatus.PASS, description=name)],
    )

    markdown = Reporter().generate_markdown(report, include_raw_output=True)
    tokens = MarkdownIt().parse(markdown)
    code_tokens = [
        child
        for token in tokens
        for child in token.children or []
        if child.type == "code_inline"
    ]

    expected = name if len(name) <= 160 else name[:160] + " ... (truncated)"
    assert [token.content for token in code_tokens] == [expected] * 3
    assert all(len(token.markup) <= 80 for token in code_tokens)


@pytest.mark.parametrize(
    ("name", "delimiter"),
    [("` ```", "``"), (" ".join("`" * size for size in range(1, 17)), "`" * 17)],
)
def test_name_code_delimiter_uses_the_shortest_unused_run(name, delimiter):
    report = InsoRunReport(
        plan_end=1,
        results=[InsoResult(id=1, status=InsoStatus.PASS, description=name)],
    )

    tokens = MarkdownIt().parse(Reporter().generate_markdown(report))
    result_code = next(
        child
        for token in tokens
        for child in token.children or []
        if child.type == "code_inline" and child.content == name
    )

    assert result_code.markup == delimiter


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a" * 511 + "*tail", "a" * 160 + " ... (truncated)"),
        ("a" * 510 + "<tail", "a" * 160 + " ... (truncated)"),
        *[
            ("a" * 159 + char + "tail", "a" * 159 + char + " ... (truncated)")
            for char in ("*", "\\", "<", "&", "`")
        ],
        ("\u754c" * 54, "\u754c" * 53 + " ... (truncated)"),
        ("a" * 160, "a" * 160),
    ],
    ids=[
        "old-escape-cut",
        "old-entity-cut",
        "star",
        "backslash",
        "html",
        "entity",
        "backtick",
        "utf8-boundary",
        "exact-budget",
    ],
)
def test_name_truncation_preserves_original_text_before_code_formatting(name, expected):
    report = InsoRunReport(
        plan_end=1,
        target_name=name,
        results=[InsoResult(id=1, status=InsoStatus.PASS, description=name)],
    )

    markdown = Reporter().generate_markdown(report)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")

    assert dom.find(".//li/strong/code").text == expected
    assert dom.find("./h2/code").text == expected
    assert dom.find("./ul/li/code").text == expected
    assert dom.findall(".//a") == []


@pytest.mark.parametrize(
    "workflow_url",
    [
        "javascript:alert(1)",
        "https://example.invalid/)\n\n# forged",
        "https://example.invalid/><img src=x>",
        "https://[invalid",
        "https://example.invalid/" + "x" * 60000,
        "https://example.invalid/\u2003path",
        "https://example.invalid/\x00path",
        "https://example.invalid/\x7fpath",
    ],
    ids=[
        "scheme",
        "newline",
        "html",
        "invalid-host",
        "oversized",
        "unicode-space",
        "nul",
        "del",
    ],
)
def test_invalid_or_oversized_workflow_urls_use_static_fallback(workflow_url):
    markdown = Reporter().generate_markdown(
        InsoRunReport(plan_end=0), workflow_url=workflow_url
    )

    assert "See the workflow run for execution details." in markdown
    assert "[workflow run]" not in markdown
    assert workflow_url not in markdown
    assert len(markdown.encode("utf-8")) < 60000


def test_workflow_url_cannot_break_out_of_its_link_destination():
    markdown = Reporter().generate_markdown(
        InsoRunReport(plan_end=0),
        workflow_url="https://example.invalid/)![image](https://example.invalid/x)",
    )

    html = MarkdownIt("commonmark", {"html": True}).render(markdown)

    assert html.count("<a href=") == 1
    assert ">workflow run</a>" in html
    assert "<img" not in html


@pytest.mark.parametrize(
    "raw_output",
    [
        "before\n```\n# forged\n```\nafter",
        "`````\n</details>\n```",
        *[
            "`" * length
            + "\n</details>\n\n# forged\n\n![image](https://example.invalid/x)\n@ghost #131"
            for length in (254, 255, 256, 8192)
        ],
    ],
    ids=["short-fence", "html", "254-ticks", "255-ticks", "256-ticks", "8192-ticks"],
)
def test_raw_output_is_literal_html_code_without_markdown_fences(raw_output):
    report = InsoRunReport(plan_end=0, raw_output=raw_output)

    markdown = Reporter().generate_markdown(report, include_raw_output=True)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")
    expected = raw_output.encode("utf-8")[:8192].decode("utf-8")

    assert dom.find(".//details/pre/code").text == expected
    assert len(dom.findall(".//details")) == 1
    assert dom.findall(".//h1") == dom.findall(".//a") == dom.findall(".//img") == []
    assert all(token.type != "fence" for token in MarkdownIt().parse(markdown))
    assert markdown.endswith("</details>")


@pytest.mark.parametrize("size", [8191, 8192, 8193])
def test_raw_output_byte_budget_boundary(size):
    report = InsoRunReport(plan_end=0, raw_output="x" * size)

    markdown = Reporter().generate_markdown(report, include_raw_output=True)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")

    assert dom.find(".//details/pre/code").text == "x" * min(size, 8192)
    assert ("Raw output truncated" in markdown) == (size > 8192)


def test_raw_output_truncation_preserves_complete_utf8_characters():
    report = InsoRunReport(plan_end=0, raw_output="\u754c" * 3000)

    markdown = Reporter().generate_markdown(report, include_raw_output=True)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")

    assert dom.find(".//details/pre/code").text == "\u754c" * 2730
    assert "Raw output truncated at 8192 bytes" in markdown


@pytest.mark.parametrize("count", [50, 51, 300])
def test_markdown_limits_displayed_results_without_changing_counts(count):
    report = InsoRunReport(
        plan_end=count,
        results=[
            InsoResult(id=index, status=InsoStatus.PASS, description=f"result-{index}")
            for index in range(1, count + 1)
        ],
    )

    markdown = Reporter().generate_markdown(report)

    assert f"**{count} test results** (all passed)" in markdown
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")
    assert [node.text for node in dom.findall(".//li/strong/code")] == [
        f"result-{index}" for index in range(1, 51)
    ]
    assert ("more results omitted" in markdown) == (count > 50)
    if count > 50:
        assert f"{count - 50} more results omitted" in markdown


@pytest.mark.parametrize(
    "raw_output",
    ["\U0001f600" * 3000, "`" * 10000, "&" * 10000],
    ids=["unicode", "backticks", "ampersands"],
)
@pytest.mark.parametrize(
    "description",
    ["[<>&*`\\\U0001f600]" * 2000, "`" * 2000],
    ids=["mixed", "backticks"],
)
def test_hostile_long_reports_fit_comments_without_losing_full_details(
    raw_output, description
):
    report = InsoRunReport(
        plan_end=300,
        target_name=description,
        raw_output=raw_output,
        results=[
            InsoResult(
                id=index + 1,
                status=list(InsoStatus)[index // 100],
                description=f"result-{index}: {description}",
            )
            for index in range(300)
        ],
    )
    reporter = Reporter()
    original_json = report.model_dump_json()
    original_junit = reporter.generate_junit(report)

    markdown = reporter.generate_markdown(
        report,
        include_raw_output=True,
        workflow_url="https://example.invalid/" + "x" * 2000,
    )

    assert len(markdown.encode("utf-8")) < 60000
    assert "**300 test results** (100 passed, 100 failed, 100 skipped)" in markdown
    assert "Insomnia Collection Failed" in markdown
    assert "250 more results omitted" in markdown
    result_lines = [
        line for line in markdown.splitlines() if line.startswith("- \u274c **")
    ]
    assert len(result_lines) == 50
    assert all(len(line.encode("utf-8")) < 600 for line in result_lines)
    assert all("(truncated)" in line for line in result_lines)
    assert "Raw output truncated at 8192 bytes" in markdown
    assert markdown.count("(truncated)") == 52
    assert report.model_dump_json() == original_json
    assert reporter.generate_junit(report) == original_junit
    suite = ElementTree.fromstring(original_junit)
    assert len(suite.findall("testcase")) == 300
    assert suite.findall("testcase")[-1].attrib["name"] == f"result-299: {description}"
    assert suite.find("testcase").attrib["classname"] == description


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


def test_native_requests_are_grouped_by_occurrence_with_failures_first():
    report = InsoRunReport(
        source="native",
        plan_end=3,
        executions=[
            RequestExecution(
                id=1,
                request_id="same",
                name="GET users",
                iteration=0,
                status_code=200,
                duration_seconds=0.125,
            ),
            RequestExecution(
                id=2,
                request_id="same",
                name="GET users",
                iteration=1,
                status_code=503,
                status="Unavailable",
                duration_seconds=1.25,
            ),
        ],
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.PASS,
                description="first request",
                execution_id=1,
            ),
            InsoResult(
                id=2, status=InsoStatus.PASS, description="status check", execution_id=2
            ),
            InsoResult(
                id=3,
                status=InsoStatus.FAIL,
                description="body check",
                execution_id=2,
                message="expected a JSON body",
                duration_seconds=0.002,
            ),
        ],
    )

    markdown = Reporter().generate_markdown(report)

    assert markdown.index("Execution 2") < markdown.index("Execution 1")
    assert markdown.index("body check") < markdown.index("status check")
    assert "HTTP 503" in markdown
    assert "1.250 s" in markdown
    assert "Iteration 2" in markdown
    assert "expected a JSON body" in markdown
    assert "**Completed requests:** 2" in markdown
    assert "requests executed" not in markdown
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")
    details = dom.findall(".//details")
    assert len(details) == 1
    assert "Execution 1" in "".join(details[0].find("summary").itertext())
    assert "first request" in "".join(details[0].itertext())


def test_request_without_assertions_and_unattributed_results_are_not_lost():
    report = InsoRunReport(
        source="native",
        plan_end=1,
        executions=[RequestExecution(id=1, name="health endpoint", status_code=204)],
        results=[
            InsoResult(
                id=1, status=InsoStatus.FAIL, description="unattributed assertion"
            )
        ],
    )

    markdown = Reporter().generate_markdown(report)

    assert "health endpoint" in markdown
    assert "unattributed assertion" in markdown
    assert "No assertions recorded" in markdown
    assert "0.000 s" not in markdown


@pytest.mark.parametrize("prior_failure", [False, True])
def test_run_error_and_incomplete_evidence_remain_visible(prior_failure):
    report = InsoRunReport(
        plan_end=int(prior_failure),
        complete=False,
        run_error=RunError(kind="timeout", message="execution exceeded its deadline"),
        results=[
            InsoResult(id=1, status=InsoStatus.FAIL, description="earlier assertion")
        ]
        if prior_failure
        else [],
    )

    markdown = Reporter().generate_markdown(report)

    assert "Insomnia Collection Failed" in markdown
    assert "### Run Error" in markdown
    assert "execution exceeded its deadline" in markdown
    assert "Incomplete" in markdown
    assert "completed results only" in markdown


@pytest.mark.parametrize("run_type", [RunType.COLLECTION, RunType.TEST])
@pytest.mark.parametrize("source", ["tap", "native"])
@pytest.mark.parametrize("complete", [False, True])
@pytest.mark.parametrize("has_results", [False, True])
def test_recovered_collection_tap_explains_missing_native_detail(
    run_type, source, complete, has_results
):
    report = InsoRunReport(
        run_type=run_type,
        source=source,
        complete=complete,
        plan_end=1,
        results=[InsoResult(id=1, status=InsoStatus.FAIL, description="fails")]
        if has_results
        else [],
    )
    markdown = Reporter().generate_markdown(report)

    expected = (
        run_type == RunType.COLLECTION
        and source == "tap"
        and not complete
        and has_results
    )
    assert (
        "recovered TAP may omit request details and assertion reasons" in markdown
    ) is expected
    assert report.failed_count == int(has_results)
    assert all(result.message is None for result in report.results)


@pytest.mark.parametrize(
    "message",
    [
        "error: mismatch | ACTUAL: a | EXPECTED: b",
        "error: mismatch | ACTUAL: a | EXPECTED: b | EXPECTED: c",
        "<img src=x>\n</code></pre></details>\n\n# forged\n![x](https://example.invalid/x)",
    ],
)
def test_failure_messages_remain_literal_without_guessing_actual_expected(message):
    report = InsoRunReport(
        plan_end=1,
        results=[
            InsoResult(
                id=1, status=InsoStatus.FAIL, description="assertion", message=message
            )
        ],
    )

    markdown = Reporter().generate_markdown(report)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")

    assert dom.find(".//pre/code").text == message
    assert dom.findall(".//h1") == dom.findall(".//img") == dom.findall(".//a") == []
    assert "**Actual:**" not in markdown
    assert "**Expected:**" not in markdown


def test_hostile_request_metadata_and_headers_are_literal():
    name = "</summary></details><img src=x> ` @ghost #131"
    report = InsoRunReport(
        source="native",
        plan_end=1,
        executions=[
            RequestExecution(
                id=1,
                name=name,
                status_code=200,
                status="<script>forged</script>",
                headers={"X-Request-ID": "</code></pre><img src=x>\n# forged"},
            )
        ],
        results=[
            InsoResult(
                id=1, status=InsoStatus.PASS, description="passes", execution_id=1
            )
        ],
    )

    markdown = Reporter().generate_markdown(report)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")

    assert dom.find(".//summary/code").text == name
    assert len(dom.findall(".//details")) == 1
    assert (
        dom.findall(".//img") == dom.findall(".//script") == dom.findall(".//h1") == []
    )
    assert "X-Request-ID" in "".join(dom.itertext())


def test_markdown_byte_budget_keeps_complete_blocks_and_unabridged_artifacts(tmp_path):
    reason = "<&\U0001f600" * 2000
    report = InsoRunReport(
        source="native",
        plan_end=300,
        raw_output="&" * 9000,
        executions=[RequestExecution(id=1, name="large request", duration_seconds=0.5)],
        results=[
            InsoResult(
                id=index,
                status=InsoStatus.FAIL,
                description=f"assertion-{index}",
                message=reason,
                execution_id=1,
                duration_seconds=0.001,
            )
            for index in range(1, 301)
        ],
    )
    before = report.model_dump_json()
    reporter = Reporter()

    markdown = reporter.generate_markdown(report, include_raw_output=True)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")
    artifact = tmp_path / "junit.xml"
    artifact.write_text(reporter.generate_junit(report), encoding="utf-8")
    suite = ElementTree.parse(artifact).getroot()

    assert len(markdown.encode("utf-8")) <= 60000
    assert "more results omitted" in markdown
    assert "300 test results" in markdown
    assert len(dom.findall(".//pre")) == len(dom.findall(".//pre/code"))
    assert len(suite.findall("testcase")) == 300
    assert suite.findall("testcase")[-1].find("failure").text == reason
    assert report.model_dump_json() == before


def test_junit_preserves_failure_details_timings_and_separate_run_error(tmp_path):
    report = InsoRunReport(
        plan_end=2,
        target_name="suite",
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.FAIL,
                description="assertion",
                message="actual < expected\x00",
                duration_seconds=0.125,
            ),
            InsoResult(
                id=2,
                status=InsoStatus.SKIP,
                description="not applicable",
                message="disabled for this environment",
                duration_seconds=0,
            ),
        ],
        run_error=RunError(
            kind="execution", message="script failed <after> assertion\x1b"
        ),
    )
    artifact = tmp_path / "junit.xml"

    artifact.write_text(Reporter().generate_junit(report), encoding="utf-8")
    suite = ElementTree.parse(artifact).getroot()
    cases = suite.findall("testcase")

    assert suite.attrib["tests"] == "3"
    assert suite.attrib["failures"] == "1"
    assert suite.attrib["errors"] == "1"
    assert suite.attrib["skipped"] == "1"
    assert cases[0].attrib["time"] == "0.125"
    assert cases[0].find("failure").text == "actual < expected\ufffd"
    assert cases[0].find("failure").attrib["message"] == "actual < expected\ufffd"
    assert cases[1].attrib["time"] == "0"
    assert cases[1].find("skipped").attrib["message"] == "disabled for this environment"
    assert cases[2].find("error").attrib["type"] == "execution"
    assert cases[2].find("error").text == "script failed <after> assertion\ufffd"
    assert "time" not in cases[2].attrib


def test_junit_does_not_invent_missing_timings():
    report = InsoRunReport(
        plan_end=1,
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.PASS,
                description="unknown duration",
            )
        ],
    )

    suite = ElementTree.fromstring(Reporter().generate_junit(report))

    assert "time" not in suite.find("testcase").attrib
    assert "time" not in suite.attrib


def test_incomplete_success_evidence_is_not_labelled_passed():
    report = InsoRunReport(
        plan_end=1,
        complete=False,
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.PASS,
                description="completed assertion",
            )
        ],
    )

    markdown = Reporter().generate_markdown(report)

    assert "Insomnia Collection Incomplete" in markdown
    assert "Insomnia Collection Passed" not in markdown


@pytest.mark.parametrize("duration", [123.123456789, 0.0000000001])
def test_junit_durations_preserve_measured_precision(duration):
    report = InsoRunReport(
        plan_end=1,
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.PASS,
                description="timed assertion",
                duration_seconds=duration,
            )
        ],
    )

    suite = ElementTree.fromstring(Reporter().generate_junit(report))

    assert float(suite.find("testcase").attrib["time"]) == duration
    assert float(suite.attrib["time"]) == duration
    assert "e" not in suite.find("testcase").attrib["time"].lower()
