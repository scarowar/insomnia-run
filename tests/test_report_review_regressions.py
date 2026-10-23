import re
from xml.etree import ElementTree

from markdown_it import MarkdownIt

from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus, RequestExecution
from insomnia_run.reporter import Reporter


def _rendered_results(markdown: str) -> list[str]:
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")
    return [node.text for node in dom.findall(".//li//strong/code")]


def test_failures_across_requests_take_result_slots_before_passes():
    report = InsoRunReport(
        source="native",
        plan_end=51,
        executions=[
            RequestExecution(id=1, name="first request"),
            RequestExecution(id=2, name="second request"),
        ],
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.FAIL,
                description="first failure",
                execution_id=1,
            ),
            *[
                InsoResult(
                    id=index + 2,
                    status=InsoStatus.PASS,
                    description=f"passing assertion {index}",
                    execution_id=1,
                )
                for index in range(49)
            ],
            InsoResult(
                id=51,
                status=InsoStatus.FAIL,
                description="later failure",
                execution_id=2,
            ),
        ],
    )

    markdown = Reporter().generate_markdown(report)
    shown = _rendered_results(markdown)

    assert "first failure" in shown
    assert "later failure" in shown
    assert len(shown) == 50
    assert len([name for name in shown if name.startswith("passing assertion")]) == 48
    assert "1 more results omitted" in markdown


def test_failures_across_requests_take_byte_budget_before_pass_messages():
    report = InsoRunReport(
        source="native",
        plan_end=32,
        executions=[
            RequestExecution(id=1, name="first request"),
            RequestExecution(id=2, name="second request"),
        ],
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.FAIL,
                description="first failure",
                execution_id=1,
            ),
            *[
                InsoResult(
                    id=index + 2,
                    status=InsoStatus.PASS,
                    description=f"passing assertion {index}",
                    message="&" * 2048,
                    execution_id=1,
                )
                for index in range(30)
            ],
            InsoResult(
                id=32,
                status=InsoStatus.FAIL,
                description="later failure",
                message="&" * 2048,
                execution_id=2,
            ),
        ],
    )

    markdown = Reporter().generate_markdown(report)
    shown = _rendered_results(markdown)

    assert "first failure" in shown
    assert "later failure" in shown
    assert len(shown) < report.total_tests < 50
    assert len(markdown.encode("utf-8")) <= 60000


def test_oversized_failure_does_not_hide_a_later_failure_that_fits():
    report = InsoRunReport(
        plan_end=7,
        results=[
            *[
                InsoResult(
                    id=index + 1,
                    status=InsoStatus.FAIL,
                    description=f"large failure {index}",
                    message="&" * 2048,
                )
                for index in range(6)
            ],
            InsoResult(id=7, status=InsoStatus.FAIL, description="small later failure"),
        ],
    )

    markdown = Reporter().generate_markdown(report)
    shown = _rendered_results(markdown)

    assert "large failure 5" not in shown
    assert "small later failure" in shown
    assert len(shown) == 6
    assert len(markdown.encode("utf-8")) <= 60000


def test_truncation_notice_counts_omitted_failures_separately():
    report = InsoRunReport(
        plan_end=60,
        results=[
            InsoResult(
                id=index + 1,
                status=InsoStatus.FAIL if index < 55 else InsoStatus.PASS,
                description=f"assertion {index}",
            )
            for index in range(60)
        ],
    )

    markdown = Reporter().generate_markdown(report)

    assert len(_rendered_results(markdown)) == 50
    assert "10 more results omitted" in markdown
    assert re.search(
        r"\b5 (?:more )?(?:failures|failed (?:results|assertions))\b", markdown
    )


def test_junit_distinguishes_repeated_assertions_by_request_and_iteration():
    executions = [
        RequestExecution(id=1, name="GET users", iteration=0),
        RequestExecution(id=2, name="GET posts", iteration=0),
        RequestExecution(id=3, name="GET users", iteration=1),
    ]
    report = InsoRunReport(
        source="native",
        target_name="API collection",
        plan_end=3,
        executions=executions,
        results=[
            InsoResult(
                id=execution.id,
                status=InsoStatus.PASS,
                description="Status is 200",
                execution_id=execution.id,
            )
            for execution in executions
        ],
    )

    suite = ElementTree.fromstring(Reporter().generate_junit(report))
    cases = suite.findall("testcase")
    identities = [(case.attrib["classname"], case.attrib["name"]) for case in cases]

    assert len(set(identities)) == len(executions)
    for execution, identity in zip(executions, identities, strict=True):
        assert execution.name in " ".join(identity)
        assert "Status is 200" in " ".join(identity)
