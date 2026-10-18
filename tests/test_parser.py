import pytest

from insomnia_run.parser import TapParser
from insomnia_run.models import InsoStatus


def test_parse_real_user_collection_output():
    raw_output = """(node:20367) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
(Use `inso --trace-deprecation ...` to show where the warning was created)
[log] Running request: My first request req_2dbae47667374c1a82ab726bbb0b91f0
[network] Response succeeded req=req_2dbae47667374c1a82ab726bbb0b91f0 status=200

Test results:
TAP version 13
1..1
ok 1 - Check if status is 200


Test: 1 passed, 1 total
    """

    report = TapParser().parse(raw_output)

    assert report.tap_version == 13
    assert report.plan_start == 1
    assert report.plan_end == 1
    assert len(report.results) == 1

    result = report.results[0]
    assert result.id == 1
    assert result.status == InsoStatus.PASS
    assert result.description == "Check if status is 200"


def test_parse_failure_scenario():
    raw_output = """
TAP version 13
1..2
ok 1 - Login Success
not ok 2 - Get User Profile
    """
    report = TapParser().parse(raw_output)
    assert report.failed_count == 1
    assert report.passed_count == 1
    assert report.results[1].status == InsoStatus.FAIL


def test_parse_without_tap_version():
    raw_output = """
ok 1 Todo API Tests GET /todos/1 returns valid JSON
ok 2 Todo API Tests GET /todos/1 returns 200
# tests 2
# pass 2
# fail 0
1..2
    """
    report = TapParser().parse(raw_output)
    assert report.passed_count == 2
    assert report.failed_count == 0
    assert len(report.results) == 2


def test_parse_mixed_results_without_version():
    raw_output = """
ok 1 Status code is 200
not ok 2 Status code is 404 (intentional failure)
ok 3 Response has userId field
# tests 3
# pass 2
# fail 1
1..3
    """
    report = TapParser().parse(raw_output)
    assert report.passed_count == 2
    assert report.failed_count == 1
    assert report.results[0].status == InsoStatus.PASS
    assert report.results[1].status == InsoStatus.FAIL
    assert report.results[2].status == InsoStatus.PASS


def test_collection_tap_blocks_are_aggregated_with_unique_ids():
    output = """Running request: first
TAP version 13
1..2
ok 1 - first assertion
not ok 2 - second assertion
Running request: second
TAP version 13
1..1
ok 1 - third assertion
"""
    report = TapParser().parse(output)

    assert (report.plan_start, report.plan_end) == (1, 3)
    assert [result.id for result in report.results] == [1, 2, 3]
    assert report.passed_count == 2
    assert report.failed_count == 1


def test_zero_plan_and_skip_directive():
    empty_report = TapParser().parse("TAP version 13\n1..0\n")
    skipped_report = TapParser().parse("ok 1 - unsupported # SKIP\n1..1\n")

    assert empty_report.plan_end == 0
    assert skipped_report.skipped_count == 1


@pytest.mark.parametrize(
    "output",
    [
        "",
        "[log] requests completed\n",
        "TAP version 13\n",
        "ok 1 - assertion without a plan\n",
        "TAP version 13\n1..2\nok 1 - incomplete\n",
        "TAP version 13\n1..1\nok 1 - first\nok 2 - extra\n",
        "TAP version 13\n1..2\nok 1 - first\nok 1 - duplicate\n",
        "TAP version 13\n1..1\nok 2 - missing first assertion\n",
        "TAP version 13\n2..2\nok 1 - invalid plan start\n",
        "TAP version 13\n1..0\nok 1 - unexpected assertion\n",
        "TAP version 13\n1..2\nok 1 - incomplete\nTAP version 13\n1..0\nok 1 - extra\n",
    ],
)
def test_missing_or_incomplete_tap_is_a_report_failure(output):
    report = TapParser().parse(output, require_tap=True)

    assert report.exit_code == 3
    assert report.run_error.kind == "protocol"
    assert not report.complete
    assert [result.id for result in report.results] == list(
        range(1, report.total_tests + 1)
    )


@pytest.mark.parametrize("output", ["", "[log] requests completed\n"])
def test_absent_tap_is_neutral_unless_required(output):
    report = TapParser().parse(output)

    assert report.results == []
    assert report.plan_end == 0


@pytest.mark.parametrize(
    "output",
    [
        "Bail out! PRIVATE_BAILOUT_REASON\n",
        "TAP version 13\n1..1\nok 1 - passes\nBail out! PRIVATE_BAILOUT_REASON\n",
        "1..1\nok 1 - passes\nBail out!PRIVATE_BAILOUT_REASON\n",
    ],
)
def test_bailout_fails_even_after_a_complete_plan_without_exposing_reason(output):
    report = TapParser().parse(output)

    assert report.exit_code == 3
    assert report.run_error.kind == "protocol"
    assert all("PRIVATE_BAILOUT_REASON" not in r.description for r in report.results)


@pytest.mark.parametrize(
    "output,passed,skipped",
    [
        ("TAP version 13\n1..0\n", 0, 0),
        ("1..0 # SKIP no supported requests\n", 0, 0),
        ("ok 1 - pending # skip unsupported\n1..1\n", 0, 1),
        ("TAP version 13\n1..1\nok 1 - passes\n", 1, 0),
        ("ok 1 - passes\n# tests 1\n# pass 1\n1..1\n", 1, 0),
        (
            "1..1\nok 1 - first\n1..1\nok 1 - second\n",
            2,
            0,
        ),
        (
            "ok 1 - first\n1..1\nok 1 - second\n1..1\n",
            2,
            0,
        ),
        (
            "TAP version 13\n1..0 # SKIP unsupported\n"
            "TAP version 13\n1..1\nok 1 - second request\n",
            1,
            0,
        ),
    ],
)
def test_complete_empty_and_skipped_plans_remain_successful(output, passed, skipped):
    report = TapParser().parse(output)

    assert report.failed_count == 0
    assert report.passed_count == passed
    assert report.skipped_count == skipped
    assert report.plan_end == passed + skipped


@pytest.mark.parametrize("suffix", ["# SKIPPER", "# skipped", "# skip_reason"])
def test_skip_directive_requires_a_complete_token(suffix):
    report = TapParser().parse(f"not ok 1 - failure {suffix}\n1..1\n")

    assert report.failed_count == 1
    assert report.skipped_count == 0


def test_failure_without_a_description_is_not_lost():
    report = TapParser().parse("ok 1 - passes\nnot ok 2\n1..2\n")

    assert [r.status for r in report.results] == [InsoStatus.PASS, InsoStatus.FAIL]


def test_description_starting_with_a_hyphen_is_preserved():
    report = TapParser().parse("ok 1 -prefixed assertion\n1..1\n")

    assert report.failed_count == 0
    assert report.results[0].description == "-prefixed assertion"
