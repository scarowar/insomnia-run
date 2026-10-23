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
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("quote", ["", '"', "'"])
def test_large_assignment_values_are_hidden_whole(quote):
    value = "private-value" * 10000
    assert (
        Redactor().redact(f"DB_PASSWORD={quote}{value}{quote} public")
        == f"DB_PASSWORD={quote}[REDACTED]{quote} public"
    )


def test_unclosed_quoted_assignment_hides_the_remaining_value():
    assert Redactor().redact('DB_PASSWORD="private-value') == 'DB_PASSWORD="[REDACTED]'


def test_large_quoted_assignment_does_not_allocate_a_regex_stack_per_character():
    program = (
        "import tracemalloc; from insomnia_run.privacy import Redactor; "
        "text = 'password=\"' + 's' * 1_000_000 + '\"'; redactor = Redactor(); "
        "tracemalloc.start(); assert redactor.redact(text) == 'password=\"[REDACTED]\"'; "
        "peak = tracemalloc.get_traced_memory()[1]; assert peak < 16 * 1024 * 1024, peak"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_nested_assignments_do_not_rescan_an_already_hidden_value():
    program = (
        "from insomnia_run.privacy import Redactor; "
        "assert Redactor().redact('token=' * 20_000 + 'private') == 'token=[REDACTED]'"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stderr
