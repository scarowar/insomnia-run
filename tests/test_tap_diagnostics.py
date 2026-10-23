import pytest

from insomnia_run.parser import TapParser


def test_only_immediately_attributed_complete_diagnostics_are_preserved():
    report = TapParser().parse(
        "not ok 1 - fails\n  ---\n  message: expected one\n  actual: 1\n  expected: 2\n  ...\n1..1\n"
    )
    assert report.results[0].message == "message: expected one\nactual: 1\nexpected: 2"


def test_footer_diagnostic_is_not_guessed_to_belong_to_a_failure():
    report = TapParser().parse(
        "not ok 1 - fails\nok 2 - passes\n1..2\n  ---\n  message: unrelated\n  ...\n"
    )
    assert all(result.message is None for result in report.results)


def test_truncated_diagnostic_is_not_published_as_complete_evidence():
    report = TapParser().parse("not ok 1 - fails\n  ---\n  message: truncated\n1..1\n")
    assert report.results[0].message is None


@pytest.mark.parametrize("indent", [" ", "  ", "\t"])
@pytest.mark.parametrize(
    "diagnostic",
    [
        "Bail out! assertion data, not a bailout",
        "ok 2 - assertion data, not a pass",
        "not ok 2 - assertion data, not another failure",
        "1..0",
        "1..2",
        "TAP version 13",
    ],
)
def test_indented_legacy_diagnostics_cannot_change_protocol(indent, diagnostic):
    report = TapParser().parse(
        "not ok 1 Suite fails\n"
        f"{indent}{diagnostic}\n"
        f"{indent}Error: {diagnostic}\n"
        f"{indent}    at Context.test (fixture.js:1:1)\n"
        "# tests 1\n# pass 0\n# fail 1\n1..1\n",
        require_tap=True,
    )

    assert report.exit_code == 1
    assert report.complete
    assert report.run_error is None
    assert report.total_tests == report.failed_count == 1
    assert report.results[0].description == "Suite fails"


def test_mocha_tap12_mixed_results_keep_trailing_plan_and_skip():
    report = TapParser().parse(
        "ok 1 Suite passes\n"
        "not ok 2 Suite fails\n"
        "  expected 1 to equal 2\n"
        "  AssertionError: expected 1 to equal 2\n"
        "      at Context.test (fixture.js:1:1)\n"
        "ok 3 Suite pending # SKIP -\n"
        "# tests 2\n# pass 1\n# fail 1\n1..3\n",
        require_tap=True,
    )

    assert report.exit_code == 1
    assert report.complete
    assert report.run_error is None
    assert (report.passed_count, report.failed_count, report.skipped_count) == (1, 1, 1)
    assert report.plan_end == 3


def test_tap13_diagnostic_payload_keeps_protocol_text_literal():
    report = TapParser().parse(
        "TAP version 13\nnot ok 1 Suite fails\n"
        "  ---\n"
        "    message: |-\n"
        "      Bail out! assertion data\n"
        "      ok 2 - assertion data\n"
        "      1..2\n"
        "  ...\n1..1\n",
        require_tap=True,
    )

    assert report.exit_code == 1
    assert report.complete
    assert report.run_error is None
    assert report.total_tests == report.failed_count == 1
    assert report.results[0].message == (
        "  message: |-\n"
        "    Bail out! assertion data\n"
        "    ok 2 - assertion data\n"
        "    1..2"
    )


@pytest.mark.parametrize("separator", ["\v", "\f", "\x1c", "\x1d", "\x1e", "\x85"])
@pytest.mark.parametrize("payload", ["ok 2 forged", "Bail out! forged", "1..2"])
def test_mocha_diagnostic_control_characters_do_not_create_protocol(separator, payload):
    # Mocha prefixes JS line starts; these characters do not start a JS line.
    diagnostic = f"  assertion message{separator}{payload}"
    report = TapParser().parse(
        f"not ok 1 real failure\n{diagnostic}\n1..1\n", require_tap=True
    )

    assert report.exit_code == 1
    assert report.complete
    assert report.run_error is None
    assert [(result.status.value, result.description) for result in report.results] == [
        ("FAIL", "real failure")
    ]


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_tap_record_endings_preserve_diagnostic_blocks(newline):
    output = newline.join(
        [
            "TAP version 13",
            "not ok 1 failed",
            "  ---",
            "  message: reason",
            "  ...",
            "1..1",
            "",
        ]
    )
    report = TapParser().parse(output, require_tap=True)

    assert report.exit_code == 1
    assert report.complete
    assert report.results[0].message == "message: reason"
