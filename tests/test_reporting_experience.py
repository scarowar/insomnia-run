"""Rendered reporting and actionable configuration errors seen by action users."""

from dataclasses import dataclass, field
from html.parser import HTMLParser
import re

from markdown_it import MarkdownIt
import pytest

from insomnia_run.action_runtime import run_action
from insomnia_run.models import InsoResult, InsoRunReport, RequestExecution
from insomnia_run.reporter import Reporter


@dataclass(eq=False)
class Element:
    tag: str
    parent: "Element | None" = None
    children: list = field(default_factory=list)

    @property
    def text(self):
        return "".join(
            child if isinstance(child, str) else child.text for child in self.children
        )

    def find(self, tag):
        return [
            element
            for child in self.children
            if isinstance(child, Element)
            for element in ([child] if child.tag == tag else []) + child.find(tag)
        ]

    def ancestors(self):
        node = self.parent
        while node:
            yield node
            node = node.parent


class Document(HTMLParser):
    def __init__(self, markdown):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.current = self.root
        self.feed(MarkdownIt("commonmark").enable("table").render(markdown))

    def handle_starttag(self, tag, attrs):
        node = Element(tag, self.current)
        self.current.children.append(node)
        if tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self.current = node

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def rendered(report, **options):
    markdown = Reporter().generate_markdown(report, **options)
    return markdown, Document(markdown).root


def overview(document):
    tables = [
        table
        for table in document.find("table")
        if [cell.text.strip() for cell in table.find("th")]
        == ["Request", "Passed", "Failed", "Skipped", "Response"]
    ]
    assert len(tables) == 1, "Expected one five-column request overview"
    return tables[0]


def failure_table(document):
    tables = [
        table
        for table in document.find("table")
        if [cell.text.strip() for cell in table.find("th")]
        == ["Request", "Assertion", "Failure"]
    ]
    assert len(tables) == 1
    return tables[0]


def request_report(count):
    return InsoRunReport(
        source="native",
        plan_end=count,
        executions=[
            RequestExecution(
                id=i, name=f"GET request-{i}", status_code=200, status="OK"
            )
            for i in range(1, count + 1)
        ],
        results=[
            InsoResult(
                id=i, execution_id=i, status="PASS", description=f"assertion-{i}"
            )
            for i in range(1, count + 1)
        ],
    )


@pytest.mark.parametrize("count", [1, 10, 11, 35])
def test_overview_discloses_once_only_when_more_than_ten_request_occurrences(count):
    _, document = rendered(request_report(count))
    table = overview(document)
    rows = [row for row in table.find("tr") if row.find("td")]
    assert len(rows) == count
    assert [row.find("td")[0].text.strip() for row in rows] == [
        f"GET request-{i}" for i in range(1, count + 1)
    ]
    disclosures = [node for node in table.ancestors() if node.tag == "details"]
    assert len(disclosures) == (1 if count > 10 else 0)
    if disclosures:
        assert not any(node.tag == "details" for node in disclosures[0].ancestors())
    assert all(
        not any(parent.tag == "details" for parent in node.ancestors())
        for node in document.find("details")
    )


def test_overview_counts_repeated_request_occurrences_for_disclosure_threshold():
    report = request_report(11)
    for execution in report.executions:
        execution.name = "GET repeated request"
    _, document = rendered(report)
    table = overview(document)
    rows = [row for row in table.find("tr") if row.find("td")]
    assert len(rows) == 11
    assert all(
        row.find("td")[0].find("code")[0].text == "GET repeated request" for row in rows
    )
    assert all(
        f"Execution {index}" in row.find("td")[0].text
        for index, row in enumerate(rows, 1)
    )
    assert len([node for node in table.ancestors() if node.tag == "details"]) == 1


@pytest.fixture
def mixed_report():
    return InsoRunReport(
        source="native",
        plan_end=4,
        executions=[
            RequestExecution(
                id=1,
                name="POST create order",
                status_code=422,
                status="Unprocessable Entity",
                headers={"X-Request-ID": "trace-123"},
            )
        ],
        results=[
            InsoResult(
                id=1,
                execution_id=1,
                status="FAIL",
                description="accepts valid order",
                message="Expected HTTP 201; received 422",
            ),
            InsoResult(
                id=2,
                execution_id=1,
                status="FAIL",
                description="returns order ID",
                message="Missing order ID in response",
            ),
            InsoResult(
                id=3, execution_id=1, status="PASS", description="retains customer name"
            ),
            InsoResult(
                id=4,
                execution_id=1,
                status="SKIP",
                description="optional tax lookup",
                message="Tax integration disabled",
            ),
        ],
    )


def test_failure_table_follows_overview_and_shows_each_assertion_once(
    mixed_report,
):
    _, document = rendered(mixed_report)
    table = failure_table(document)
    assert document.find("table").index(overview(document)) < document.find(
        "table"
    ).index(table)
    assert not any(node.tag == "details" for node in table.ancestors())
    rows = [
        [cell.text.strip() for cell in row.find("td")]
        for row in table.find("tr")
        if row.find("td")
    ]
    assert rows == [
        ["POST create order", "accepts valid order", "Expected HTTP 201; received 422"],
        ["POST create order", "returns order ID", "Missing order ID in response"],
    ]
    assert not document.find("h4")
    assert "Execution 1" not in document.text


def test_failure_table_uses_first_line_and_one_flat_disclosure_keeps_full_reason(
    mixed_report,
):
    mixed_report.results[
        0
    ].message = "Expected HTTP 201; received 422\nDetailed response evidence"
    _, document = rendered(mixed_report)
    table = failure_table(document)
    rows = [row.find("td") for row in table.find("tr") if row.find("td")]
    assert rows[0][2].text == "Expected HTTP 201; received 422"
    assert "Detailed response evidence" not in table.text
    owners = [
        node
        for node in document.find("details")
        if node.find("summary")[0].text == "Failure output"
    ]
    assert len(owners) == 1
    assert not any(node.tag == "details" for node in owners[0].ancestors())
    assert mixed_report.results[0].message in owners[0].text
    assert "retains customer name" not in owners[0].text


def test_compact_totals_are_one_row_and_target_appears_once(mixed_report):
    mixed_report.target_name = "Example API collection"
    _, document = rendered(mixed_report)
    assert document.find("h2")[0].text == "Insomnia Run"
    assert document.text.count("Example API collection") == 1
    totals = [
        table
        for table in document.find("table")
        if [cell.text.strip() for cell in table.find("th")]
        == ["Requests", "Assertions", "Passed", "Failed", "Skipped"]
    ]
    assert len(totals) == 1
    assert [
        [cell.text.strip() for cell in row.find("td")]
        for row in totals[0].find("tr")
        if row.find("td")
    ] == [["1", "4", "1", "2", "1"]]
    assert re.search(r"Result:\s*Failed", document.text)


@pytest.mark.parametrize(
    "text",
    [
        "literal | columns | `ticks`",
        "<img src=x> ![tracking](https://example.invalid/x) & value",
        "**bold** [click](https://example.invalid) @ghost #1",
    ],
)
def test_failure_table_assertions_and_first_line_reasons_are_literal(
    text, mixed_report
):
    mixed_report.results = [
        InsoResult(
            id=1,
            execution_id=1,
            status="FAIL",
            description=text,
            message=text + "\nfull diagnostic detail",
        )
    ]
    mixed_report.plan_end = 1
    _, document = rendered(mixed_report)
    rows = [
        row.find("td") for row in failure_table(document).find("tr") if row.find("td")
    ]
    assert len(rows) == 1
    assert len(rows[0]) == 3
    assert [cell.text for cell in rows[0][1:]] == [text, text]
    for cell in rows[0][1:]:
        assert not cell.find("img") and not cell.find("a") and not cell.find("strong")
    assert "full diagnostic detail" not in failure_table(document).text


def test_passed_and_skipped_evidence_and_headers_have_separate_flat_disclosures(
    mixed_report,
):
    _, document = rendered(mixed_report)
    disclosures = document.find("details")
    for node in disclosures:
        assert not any(parent.tag == "details" for parent in node.ancestors())
        assert node.find("summary")
        assert node.text.strip() != node.find("summary")[0].text.strip()
    owners = []
    for text in (
        "retains customer name",
        "optional tax lookup",
        "X-Request-ID: trace-123",
    ):
        matches = [node for node in disclosures if text in node.text]
        assert len(matches) == 1, f"Expected one disclosure for {text}"
        owners.append(matches[0])
    assert len({id(node) for node in owners}) == 3


def test_overview_counts_assertions_instead_of_calling_every_request_passed(
    mixed_report,
):
    mixed_report.executions.append(
        RequestExecution(id=2, name="GET health without assertions")
    )
    _, document = rendered(mixed_report)
    rows = [row.find("td") for row in overview(document).find("tr") if row.find("td")]
    assert len(rows) == 2
    assert [cell.text.strip() for cell in rows[0][1:4]] == ["1", "2", "1"]
    assert "422" in rows[0][4].text
    assert [cell.text.strip() for cell in rows[1][1:4]] == ["0", "0", "0"]
    assert "✅" not in rows[1][0].text
    assert "unknown" in rows[1][4].text.lower()


def test_empty_and_skipped_runs_keep_neutral_status_and_no_empty_disclosures():
    for results, status in (
        ([], "no assertions"),
        (
            [
                InsoResult(
                    id=1, execution_id=1, status="SKIP", description="disabled check"
                )
            ],
            "skipped",
        ),
    ):
        report = InsoRunReport(
            source="native",
            plan_end=len(results),
            executions=[RequestExecution(id=1, name="GET optional")],
            results=results,
        )
        _, document = rendered(report)
        assert re.search(rf"Result:\s*{status}", document.text, re.I)
        row = [row for row in overview(document).find("tr") if row.find("td")][0]
        assert [cell.text.strip() for cell in row.find("td")[1:4]] == (
            ["0", "0", "0"] if not results else ["0", "0", "1"]
        )
        for disclosure in document.find("details"):
            assert disclosure.text.strip() != disclosure.find("summary")[0].text.strip()


@pytest.mark.parametrize(
    "name",
    [
        "GET /a|b",
        "POST /`ticks`",
        "GET /<img src=x>&value",
        "GET literal · punctuation — retained",
    ],
)
def test_hostile_request_names_preserve_table_columns_and_literal_text(name):
    report = request_report(1)
    report.executions[0].name = name
    _, document = rendered(report)
    rows = [row for row in overview(document).find("tr") if row.find("td")]
    assert len(rows) == 1
    assert len(rows[0].find("td")) == 5
    assert rows[0].find("td")[0].text.strip() == name
    assert not document.find("img")
    assert not document.find("script")


def test_authored_report_text_uses_no_middle_dot_or_em_dash_separators(mixed_report):
    markdown, _ = rendered(mixed_report)
    assert "·" not in markdown
    assert "—" not in markdown


def test_raw_output_is_opt_in_in_its_own_non_nested_disclosure(mixed_report):
    mixed_report.raw_output = "raw-evidence-marker"
    _, without_raw = rendered(mixed_report)
    assert "raw-evidence-marker" not in without_raw.text
    _, document = rendered(mixed_report, include_raw_output=True)
    owners = [
        node for node in document.find("details") if "raw-evidence-marker" in node.text
    ]
    assert len(owners) == 1
    assert not any(node.tag == "details" for node in owners[0].ancestors())
    assert "retains customer name" not in owners[0].text


def action_environment(tmp_path):
    return {
        "COMMAND": "collection",
        "RUNNER_TEMP": str(tmp_path),
        "WORKING_DIR": "fixture.yaml",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
    }


def test_incompatible_action_input_identifies_name_and_recovery_without_value(
    tmp_path, capsys
):
    sentinel = "private-pattern-sentinel-1742"
    environment = action_environment(tmp_path)
    environment.update(COMMAND="test", REQUEST_NAME_PATTERN=sentinel)
    assert run_action(environment) == 2
    diagnostic = capsys.readouterr().out.lower()
    assert "request-name-pattern" in diagnostic
    assert "test" in diagnostic
    assert "collection" in diagnostic
    assert "remove" in diagnostic or "only" in diagnostic
    assert sentinel not in diagnostic
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "variable,name,minimum,unit,invalid",
    [
        (variable, name, minimum, unit, invalid)
        for variable, name, minimum, unit in (
            ("REQUEST_TIMEOUT", "request-timeout", 0, "milliseconds"),
            ("EXECUTION_TIMEOUT", "execution-timeout", 1, "seconds"),
            ("DELAY_REQUEST", "delay-request", 0, "milliseconds"),
            ("ITERATION_COUNT", "iteration-count", 1, "iterations"),
        )
        for invalid in ["private-numeric-sentinel-1742", "1.5", "5ms", "-1"]
        + (["0"] if minimum == 1 else [])
    ],
)
def test_invalid_numeric_action_input_explains_name_type_range_and_units_without_value(
    tmp_path, capsys, variable, name, minimum, unit, invalid
):
    environment = action_environment(tmp_path)
    environment[variable] = invalid
    assert run_action(environment) == 2
    diagnostic = capsys.readouterr().out.lower()
    assert name in diagnostic
    assert "integer" in diagnostic
    assert unit in diagnostic
    assert (
        re.search(
            rf"(?:>=\s*{minimum}|at least\s+{minimum}|minimum\s+{minimum}|{minimum}\s+or (?:greater|more))",
            diagnostic,
        )
        or (minimum == 0 and "non-negative" in diagnostic)
        or (minimum == 1 and ("positive" in diagnostic or "> 0" in diagnostic))
    )
    assert "private-numeric-sentinel-1742" not in diagnostic
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("code", [200, None])
@pytest.mark.parametrize(
    "status",
    [
        "![tracking](https://example.invalid/x)",
        "[click](https://example.invalid) **bold** `ticks` @ghost #1 | text",
    ],
)
def test_response_status_is_literal_inside_request_table(code, status):
    report = request_report(1)
    report.executions[0].status_code = code
    report.executions[0].status = status
    _, document = rendered(report)
    cells = [row.find("td") for row in overview(document).find("tr") if row.find("td")][
        0
    ]
    assert len(cells) == 5
    assert cells[4].text == (f"HTTP {code} {status}" if code is not None else status)
    assert not cells[4].find("img")
    assert not cells[4].find("a")
    assert not cells[4].find("strong")


def test_whitespace_only_raw_diagnostics_do_not_create_empty_disclosure():
    report = InsoRunReport(plan_end=0, raw_output=" \n\t")
    _, document = rendered(report, include_raw_output=True)
    assert not document.find("details")


def test_many_assertions_in_one_request_keep_failure_evidence_within_budget():
    report = request_report(1)
    report.results = [
        InsoResult(id=i, execution_id=1, status="FAIL", description=f"large-check-{i}")
        for i in range(6000)
    ]
    report.plan_end = len(report.results)
    before = report.model_dump_json()
    markdown, document = rendered(report)
    assert len(markdown.encode()) <= 60000
    assert "large-check-0" in document.text
    assert "failed assertions omitted" in document.text
    assert report.model_dump_json() == before


def test_failure_previews_do_not_crowd_out_failure_identities_that_fit():
    report = InsoRunReport(
        source="native",
        plan_end=100,
        executions=[RequestExecution(id=1, name="GET orders")],
        results=[
            InsoResult(id=i, execution_id=1, status="FAIL", description=f"check-{i}")
            for i in range(1, 101)
        ],
    )
    expected = [f"check-{i}" for i in range(1, 101)]
    for reason in (None, "&" * 160):
        for result in report.results:
            result.message = reason
        before = report.model_dump_json()
        markdown, document = rendered(report, max_bytes=60000)
        rows = [
            row.find("td")
            for row in failure_table(document).find("tr")
            if row.find("td")
        ]
        assert [cells[1].text for cells in rows] == expected
        assert len(markdown.encode("utf-8")) <= 60000
        assert report.model_dump_json() == before


def test_tiny_budget_reports_all_rejected_failure_rows_without_empty_disclosures():
    report = InsoRunReport(
        source="native",
        plan_end=6000,
        executions=[RequestExecution(id=1, name="GET orders")],
        results=[
            InsoResult(
                id=i,
                execution_id=1,
                status="FAIL",
                description=f"check-{i} " + "&" * 200,
            )
            for i in range(6000)
        ],
    )
    before = report.model_dump_json()
    markdown, document = rendered(report, max_bytes=1000)
    assert len(markdown.encode("utf-8")) <= 1000
    assert "6000 failed assertions omitted" in document.text
    assert not [
        table
        for table in document.find("table")
        if [cell.text for cell in table.find("th")]
        == ["Request", "Assertion", "Failure"]
    ]
    assert not document.find("details")
    assert report.model_dump_json() == before
