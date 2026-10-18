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
