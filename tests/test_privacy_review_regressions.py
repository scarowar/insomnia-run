import subprocess
import sys

import pytest

from insomnia_run.privacy import Redactor, mask_commands


@pytest.mark.parametrize(
    "env_vars",
    [
        ["RETRIES=1", "EXPECTED_STATUS=200", "DEBUG=true"],
        {"RETRIES": "1", "EXPECTED_STATUS": "200", "DEBUG": "true"},
        ["RETRIES=1&EXPECTED_STATUS=200&DEBUG=true"],
    ],
)
def test_short_noncredential_environment_values_preserve_report_text(env_vars):
    redactor = Redactor(env_vars=env_vars)
    text = "1 assertion expected status 200 with DEBUG=true"

    assert redactor.redact(text) == text


@pytest.mark.parametrize("value", ["1", "200", "true"])
def test_short_noncredential_environment_values_do_not_mask_action_outputs(value):
    redactor = Redactor(env_vars=[f"SETTING={value}"])

    assert mask_commands(redactor.values) == []


@pytest.mark.parametrize("value", ["1", "200", "true"])
def test_explicit_short_redaction_values_are_always_redacted_and_masked(value):
    redactor = Redactor(values=[value])

    assert redactor.redact(value) == "[REDACTED]"
    assert mask_commands(redactor.values) == [f"::add-mask::{value}"]


@pytest.mark.parametrize(
    "name", ["GITHUB_TOKEN", "DB_PASSWORD", "AWS_SECRET_ACCESS_KEY", "X_API_KEY"]
)
@pytest.mark.parametrize("separator", ["=", ": "])
def test_prefixed_credential_assignments_are_scrubbed_without_known_values(
    name, separator
):
    assert Redactor().redact(f"{name}{separator}private-value") == (
        f"{name}{separator}[REDACTED]"
    )


@pytest.mark.parametrize("env_vars", [["GITHUB_TOKEN=1"], {"GITHUB_TOKEN": "1"}])
def test_short_credential_environment_values_are_redacted_and_masked(env_vars):
    redactor = Redactor(env_vars=env_vars)

    assert redactor.redact("1") == "[REDACTED]"
    assert mask_commands(redactor.values) == ["::add-mask::1"]


def test_long_dotted_non_url_input_finishes_within_a_bounded_time():
    program = (
        "from insomnia_run.privacy import Redactor; "
        "text = 'a.' * 50_000; "
        "assert Redactor().redact(text) == text"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("Redacting 100 KB of dotted text exceeded five seconds")

    assert result.returncode == 0, result.stderr
