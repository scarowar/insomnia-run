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
