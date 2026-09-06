from insomnia_run.models import InsoStatus, RunType
from insomnia_run.parser import TapParser


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


# --- Parser v2: verbatim dialect fixtures from findings/01 (real 13.2.0 binary captures) ---

MOCHA_TAP12_TWO_TESTS = """not ok 1 suite-a always fails
  expected 1 to equal 2
  AssertionError: expected 1 to equal 2
      at Context.<anonymous> (/tmp/insomnia-testing/129fb2d3-test.ts:46:18)
      at process.processImmediate (node:internal/timers:504:21)
ok 2 suite-a always passes
# tests 2
# pass 1
# fail 1
1..2
"""

MOCHA_TAP12_BAIL = """not ok 1 suite-b first fails
  expected 1 to equal 2
  AssertionError: expected 1 to equal 2
      at Context.<anonymous> (/tmp/insomnia-testing/17217f4e-test.ts:46:18)
      ...
# tests 1
# pass 0
# fail 1
1..1
"""

INSO_TAP13_TWO_REQUESTS = """Running request: passes req_c1
[plugin] Loading bundled plugin @kong/insomnia-plugin-external-vault from /snapshot/insomnia/node_modules/index.js
[plugin] Loading bundled plugin @kong/insomnia-plugin-ai from /snapshot/insomnia/node_modules/index.js
[network] Response succeeded req=req_c1 status=200

Test results:
TAP version 13
1..1
ok 1 - passes: status 200


Test: 1 passed, 1 total


Running request: fails req_c2
[network] Response succeeded req=req_c2 status=200

Test results:
TAP version 13
1..1
not ok 1 - fails: value mismatch


Test: 1 failed, 1 total

error: AssertionError: expected 1 to equal 2 | ACTUAL: 1 | EXPECTED: 2

Test Requests: 1 failed, 1 passed, 2 total
Tests:         1 failed, 1 passed, 2 total
"""

INSO_TAP13_ITERATIONS = """TAP version 13
1..1
ok 1 - passes: status 200

Test: 1 passed, 1 total

TAP version 13
1..1
not ok 1 - fails: value mismatch

Test: 1 failed, 1 total

error: AssertionError: expected 1 to equal 2 | ACTUAL: 1 | EXPECTED: 2
"""


class TestParserV2MochaDialect:
    def test_run_test_parses_plan_at_end_and_captures_message(self):
        report = TapParser().parse(MOCHA_TAP12_TWO_TESTS, RunType.TEST)

        assert report.tap_version == 12
        assert report.plan_end == 2
        assert report.total_tests == 2
        assert report.results[0].status == InsoStatus.FAIL
        assert report.results[0].message == "expected 1 to equal 2"
        assert report.results[1].status == InsoStatus.PASS
        assert report.results[1].message is None

    def test_run_test_bail_fixture(self):
        report = TapParser().parse(MOCHA_TAP12_BAIL, RunType.TEST)

        assert report.total_tests == 1
        assert report.results[0].status == InsoStatus.FAIL
        assert report.results[0].message == "expected 1 to equal 2"
        assert report.plan_end == 1

    def test_stack_frames_not_in_message(self):
        report = TapParser().parse(MOCHA_TAP12_TWO_TESTS, RunType.TEST)

        assert "at Context" not in report.results[0].message
        assert "AssertionError" not in report.results[0].message


class TestParserV2InsoTap13Dialect:
    def test_run_collection_multi_document(self):
        report = TapParser().parse(INSO_TAP13_TWO_REQUESTS, RunType.COLLECTION)

        assert report.plan_end == 2
        assert report.total_tests == 2
        assert report.results[0].id == 1
        assert report.results[0].description == "passes: status 200"
        assert report.results[0].status == InsoStatus.PASS
        assert report.results[1].id == 2
        assert report.results[1].description == "fails: value mismatch"
        assert report.results[1].status == InsoStatus.FAIL

    def test_run_collection_harvests_footer_error_as_message(self):
        report = TapParser().parse(INSO_TAP13_TWO_REQUESTS, RunType.COLLECTION)

        assert report.results[1].message == (
            "AssertionError: expected 1 to equal 2 | ACTUAL: 1 | EXPECTED: 2"
        )

    def test_paired_footer_errors_do_not_duplicate_in_diagnostics(self):
        report = TapParser().parse(INSO_TAP13_TWO_REQUESTS, RunType.COLLECTION)

        assert report.diagnostics == []

    def test_unpaired_footer_errors_land_in_diagnostics(self):
        raw = INSO_TAP13_ITERATIONS + ("error: SECOND failure | ACTUAL: x | EXPECTED: y\n")
        report = TapParser().parse(raw, RunType.COLLECTION)

        # 2 errors vs 1 failing result: positional attribution would be a
        # guess, so nothing is paired and both errors land in diagnostics.
        assert report.results[0].message is None
        assert report.results[1].message is None
        assert report.diagnostics == [
            "AssertionError: expected 1 to equal 2 | ACTUAL: 1 | EXPECTED: 2",
            "SECOND failure | ACTUAL: x | EXPECTED: y",
        ]

    def test_renumbering_across_duplicate_ids(self):
        report = TapParser().parse(INSO_TAP13_ITERATIONS, RunType.COLLECTION)

        assert [r.id for r in report.results] == [1, 2]
        assert report.plan_end == 2
        assert report.results[1].message is not None

    def test_noise_lines_ignored(self):
        report = TapParser().parse(INSO_TAP13_TWO_REQUESTS, RunType.COLLECTION)

        descriptions = " ".join(r.description for r in report.results)
        assert "Running request" not in descriptions
        assert "plugin" not in descriptions


class TestParserV2Common:
    def test_skip_directive_stripped_and_classified(self):
        report = TapParser().parse(
            "TAP version 13\n1..2\nok 1 - real test\nnot ok 2 - skipped one # SKIP\n",
            RunType.COLLECTION,
        )

        assert report.results[0].status == InsoStatus.PASS
        assert report.results[1].status == InsoStatus.SKIP
        assert report.results[1].description == "skipped one"

    def test_default_run_type_is_collection(self):
        report = TapParser().parse("TAP version 13\n1..1\nok 1 - x\n")

        assert report.total_tests == 1

    def test_plan_results_mismatch_is_flagged_in_diagnostics(self):
        report = TapParser().parse("TAP version 13\n1..3\nok 1 - a\nok 2 - b\n")

        assert any("declares 3" in d for d in report.diagnostics)

    def test_matching_plan_does_not_warn(self):
        report = TapParser().parse("TAP version 13\n1..2\nok 1 - a\nok 2 - b\n")

        assert report.diagnostics == []

    def test_missing_plan_does_not_warn(self):
        report = TapParser().parse("ok 1 - a\n")

        assert report.diagnostics == []
