"""Exercise report contracts with generated Unicode and repeated TAP blocks."""

from xml.etree import ElementTree

from hypothesis import example, given, settings, strategies as st

from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus
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
