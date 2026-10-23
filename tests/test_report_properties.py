"""Exercise report contracts with generated Unicode and repeated TAP blocks."""

from xml.etree import ElementTree

from hypothesis import example, given, settings, strategies as st

from insomnia_run.models import (
    InsoResult,
    InsoRunReport,
    InsoStatus,
    RequestExecution,
    RunError,
)
from markdown_it import MarkdownIt
from insomnia_run.parser import TapParser
from insomnia_run.reporter import Reporter


def xml_safe(value):
    return "".join(
        char
        if (
            ord(char) in (9, 10, 13)
            or 0x20 <= ord(char) <= 0xD7FF
            or 0xE000 <= ord(char) <= 0xFFFD
            or 0x10000 <= ord(char) <= 0x10FFFF
        )
        else "\ufffd"
        for char in value
    )


@settings(max_examples=500, derandomize=True)
@example(description="NUL\x00ANSI\x1b[31m", target="suite\ufffe")
@example(description="line\r\nwith\ttabs", target="suite\nname")
@example(description="surrogate\ud800", target="suite\udfff")
@example(
    description="\t\n\r\ud7ff\ue000\ufffd\U00010000\U0010ffff", target="boundaries"
)
@given(description=st.text(max_size=300), target=st.text(min_size=1, max_size=100))
def test_junit_is_valid_and_preserves_unicode(description, target):
    report = InsoRunReport(
        plan_end=3,
        target_name=target,
        raw_output="private raw logs",
        results=[
            InsoResult(id=index, status=status, description=description)
            for index, status in enumerate(InsoStatus, 1)
        ],
    )

    xml = Reporter().generate_junit(report)
    suite = ElementTree.fromstring(xml)
    cases = suite.findall("testcase")

    assert len(cases) == int(suite.attrib["tests"]) == 3
    assert suite.attrib["failures"] == suite.attrib["skipped"] == "1"
    assert all(case.attrib["name"] == xml_safe(description) for case in cases)
    assert all(case.attrib["classname"] == xml_safe(target) for case in cases)
    assert suite.find("./testcase/failure").attrib["message"] == xml_safe(description)
    assert "private raw logs" not in xml
    xml.encode("utf-8")


@settings(max_examples=300, derandomize=True)
@given(blocks=st.lists(st.lists(st.booleans(), max_size=15), max_size=10))
def test_repeated_tap_blocks_keep_counts_and_ids(blocks):
    lines = []
    expected = []
    for block in blocks:
        lines.extend(["TAP version 13", f"1..{len(block)}"])
        for index, passed in enumerate(block, 1):
            lines.append(f"{'ok' if passed else 'not ok'} {index} - assertion")
            expected.append(InsoStatus.PASS if passed else InsoStatus.FAIL)

    report = TapParser().parse("\n".join(lines))

    assert report.plan_end == report.total_tests == len(expected)
    assert [result.status for result in report.results] == expected
    assert [result.id for result in report.results] == list(range(1, len(expected) + 1))
    assert report.passed_count + report.failed_count + report.skipped_count == len(
        expected
    )


@settings(max_examples=100, derandomize=True)
@example(name="surrogate\ud800", message="</code></pre></details>\n# forged", count=60)
@example(name="&" * 200, message="<&\U0001f600" * 3000, count=60)
@given(
    name=st.text(max_size=200),
    message=st.text(max_size=2000),
    count=st.integers(min_value=0, max_value=70),
)
def test_native_markdown_is_bounded_literal_and_does_not_mutate_report(
    name, message, count
):
    report = InsoRunReport(
        source="native",
        plan_end=count,
        target_name=name,
        complete=False,
        run_error=RunError(kind="execution", message=message),
        raw_output="&" * 9000,
        executions=[
            RequestExecution(
                id=index,
                request_id="repeated-request",
                name=name,
                status_code=200,
                iteration=index - 1,
                headers={"X-Request-ID": message},
            )
            for index in range(1, count + 1)
        ],
        results=[
            InsoResult(
                id=index,
                status=InsoStatus.FAIL if index % 2 else InsoStatus.PASS,
                description=name,
                message=message,
                execution_id=index,
            )
            for index in range(1, count + 1)
        ],
    )
    before = report.model_dump()

    markdown = Reporter().generate_markdown(report, include_raw_output=True)
    dom = ElementTree.fromstring(f"<div>{MarkdownIt().render(markdown)}</div>")

    assert len(markdown.encode("utf-8")) <= 60000
    assert dom.findall(".//img") == dom.findall(".//a") == dom.findall(".//h1") == []
    assert len(dom.findall(".//details")) == markdown.count("</details>")
    assert len(dom.findall(".//pre")) == len(dom.findall(".//pre/code"))
    assert report.model_dump() == before


@settings(max_examples=200, derandomize=True)
@example(message="NUL\x00ANSI\x1b[31m", error="surrogate\udfff")
@given(message=st.text(max_size=300), error=st.text(max_size=300))
def test_junit_messages_and_run_errors_preserve_sanitized_unicode(message, error):
    report = InsoRunReport(
        plan_end=1,
        results=[
            InsoResult(
                id=1, status=InsoStatus.FAIL, description="assertion", message=message
            )
        ],
        run_error=RunError(kind="protocol", message=error),
    )

    suite = ElementTree.fromstring(Reporter().generate_junit(report))
    failure = suite.find("./testcase/failure")
    run_error = suite.find("./testcase/error")

    assert suite.attrib["tests"] == "2"
    assert suite.attrib["failures"] == suite.attrib["errors"] == "1"
    assert failure.attrib["message"] == xml_safe(message or "assertion")
    expected_failure = message if message else "Inso reported this test as failed."
    assert failure.text == xml_safe(expected_failure).replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    assert (run_error.text or "") == xml_safe(error).replace("\r\n", "\n").replace(
        "\r", "\n"
    )
