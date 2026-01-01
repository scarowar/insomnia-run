import pytest
from insomnia_run.parser import TapParser
from insomnia_run.models import TestStatus

def test_parse_real_user_collection_output():
    """
    Test the parser against the exact snippet provided by the user.
    """
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
    assert result.status == TestStatus.PASS
    assert result.description == "Check if status is 200"

def test_parse_failure_scenario():
    """
    Test a hypothetical failure case based on standard TAP.
    """
    raw_output = """
TAP version 13
1..2
ok 1 - Login Success
not ok 2 - Get User Profile
    """
    report = TapParser().parse(raw_output)
    assert report.failed_count == 1
    assert report.passed_count == 1
    assert report.results[1].status == TestStatus.FAIL
