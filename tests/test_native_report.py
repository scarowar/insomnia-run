import json

import pytest

from insomnia_run.native import parse_native_report, validate_capture_headers


def native_report(**overrides):
    return {
        "executions": [
            {
                "request": {"_id": "req_a", "name": "Login", "description": "private"},
                "response": {"status": "OK", "code": 200, "responseTime": 20},
                "iteration": 0,
                "tests": [
                    {"testCase": "works", "status": "passed", "executionTime": 1},
                    {
                        "testCase": "reason",
                        "status": "failed",
                        "executionTime": 2,
                        "errorMessage": "expected 1 to equal 2",
                    },
                    {"testCase": "later", "status": "skipped", "executionTime": 0},
                ],
            },
        ],
        "proxy": {"url": "private"},
        "environment": {"data": "private"},
        "stats": {"requests": {"failed": 0}},
        "error": None,
        **overrides,
    }


def test_native_projection_preserves_assertions_and_drops_unpublished_data():
    report = parse_native_report(json.dumps(native_report()))
    assert (report.passed_count, report.failed_count, report.skipped_count) == (1, 1, 1)
    assert report.results[1].message == "expected 1 to equal 2"
    assert report.results[1].duration_seconds == 0.002
    assert report.executions[0].duration_seconds == 0.02
    assert report.request_count == 1
    assert report.exit_code == 1
    assert "private" not in report.model_dump_json()


def test_native_error_is_not_hidden_by_earlier_assertion_failure():
    report = parse_native_report(json.dumps(native_report(error="script stopped")))
    assert report.run_error.message == "script stopped"
    assert report.exit_code == 3
    assert not report.complete
    assert report.request_count == 1
    assert report.failed_count == 1


def test_repeated_request_has_separate_occurrence_ids():
    data = native_report()
    data["executions"] *= 2
    report = parse_native_report(json.dumps(data))
    assert [e.id for e in report.executions] == [1, 2]
    assert [e.request_id for e in report.executions] == ["req_a", "req_a"]
    assert [r.id for r in report.results] == list(range(1, 7))


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "[]",
        "{}",
        '{"executions":null}',
        '{"executions":[{"request":{},"tests":[{"status":"invented"}]}]}',
        '{"executions":[],"error":123}',
    ],
)
def test_malformed_native_report_is_rejected(payload):
    with pytest.raises(ValueError):
        parse_native_report(payload)


def test_native_duration_rejects_nonfinite_values():
    data = native_report()
    data["executions"][0]["tests"][0]["executionTime"] = float("nan")
    payload = json.dumps(data)
    with pytest.raises(ValueError):
        parse_native_report(payload)


def test_only_explicit_response_headers_from_native_mapping_are_published():
    data = native_report()
    data["executions"][0]["response"]["headers"] = {
        "X-Request-ID": "correlation",
        "Authorization": "private",
        "X-Unlisted": "private",
    }
    data["executions"][0]["response"]["data"] = "private"
    report = parse_native_report(json.dumps(data), capture_headers=["x-request-id"])
    assert report.executions[0].headers == {"x-request-id": "correlation"}
    assert "private" not in report.model_dump_json()


@pytest.mark.parametrize(
    "name",
    ["auth", "x-auth", "bearer", "basic", "x-csrf", "x-xsrf", "session-id", "jwt"],
)
def test_credential_bearing_header_aliases_cannot_be_captured(name):
    with pytest.raises(ValueError):
        validate_capture_headers([name])


def test_oversized_header_is_omitted_instead_of_exposing_a_secret_prefix():
    data = native_report()
    data["executions"][0]["response"]["headers"] = {
        "X-Request-ID": "a" * 2038 + "TOPSECRET_private-value"
    }
    report = parse_native_report(json.dumps(data), capture_headers=["x-request-id"])
    assert report.executions[0].headers == {}


def test_nullable_response_does_not_crash_header_projection():
    data = native_report(error="request stopped")
    data["executions"][0]["response"] = None
    report = parse_native_report(json.dumps(data), capture_headers=["x-request-id"])
    assert report.exit_code == 3
    assert report.executions[0].headers == {}
