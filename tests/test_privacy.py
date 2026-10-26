import base64
import json
from enum import Enum
from urllib.parse import quote, quote_plus

import pytest
from pydantic import BaseModel, Field

from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus
from insomnia_run.privacy import Redactor, escape_workflow_command, mask_commands


def test_known_values_are_replaced_longest_first_without_redacting_the_marker():
    redactor = Redactor(["a", "alphabet", "", "a"])
    assert redactor.redact("alphabet a z") == "[REDACTED] [REDACTED] z"


@pytest.mark.parametrize("value", ["R", "[", "REDACTED"])
def test_short_known_values_do_not_corrupt_redaction_marker(value):
    assert Redactor([value]).redact("Authorization: Bearer private") == (
        "Authorization: [REDACTED]"
    )


@pytest.mark.parametrize("encode", [quote, quote_plus, lambda s: json.dumps(s)[1:-1]])
def test_encoded_known_values(encode):
    value = 'hello /+?"\nworld'
    assert redactor_free(Redactor([value]).redact(encode(value)), encode(value))


def redactor_free(text, secret):
    return secret not in text and "[REDACTED]" in text


def test_percent_decoded_supplied_values_and_percent_encoding_case():
    redactor = Redactor(["word%2Fwith%20space"])
    assert redactor.redact("word/with space word%2fwith%20space") == (
        "[REDACTED] [REDACTED]"
    )


def test_base64_known_values_and_decoded_input():
    value = "synthetic value!"
    encoded = base64.b64encode(value.encode()).decode()
    assert Redactor([value]).redact(encoded) == "[REDACTED]"
    assert Redactor([encoded]).redact(value) == "[REDACTED]"


@pytest.mark.parametrize(
    "env_vars",
    [["NAME=private=value", "EMPTY=", "no-assignment"], {"NAME": "private=value"}],
)
def test_environment_values_do_not_require_secret_looking_names(env_vars):
    assert Redactor(env_vars=env_vars).redact("private=value") == "[REDACTED]"


@pytest.mark.parametrize(
    ("text", "hidden"),
    [
        ("https://user:credential@example.test/path", "user:credential"),
        ("proxy http://user:credential@proxy.test:8080/", "credential"),
        ("https://example.test/?access_token=private&ok=yes", "private"),
        ("https://example.test/?API%5FKEY=private&ok=yes", "private"),
        ("https://example.test/?X-Amz-Signature=private&ok=yes", "private"),
        ("Authorization: Bearer private\nContent-Type: text/plain", "private"),
        ("proxy-authorization: Basic private\r\n", "private"),
        ('{"X-API-Key": "private"}', "private"),
        ('{"password": "private"}', "private"),
        ("Cookie: session=private; other=value\n", "private"),
        ("Set-Cookie: session=private; HttpOnly\n", "private"),
        ("client_secret=private next", "private"),
    ],
)
def test_credential_patterns_are_removed_without_known_values(text, hidden):
    result = Redactor().redact(text)
    assert hidden not in result
    assert "[REDACTED]" in result


def test_normal_urls_and_text_remain_readable():
    text = "GET https://example.test/path?limit=5&name=alice returned 200"
    assert Redactor().redact(text) == text


def test_redacted_report_is_a_separate_model_with_status_preserved():
    report = InsoRunReport(
        target_name="private",
        raw_output="private",
        plan_end=1,
        results=[InsoResult(id=1, status=InsoStatus.FAIL, description="private")],
    )
    redacted = Redactor(["private", "FAIL"]).redact_report(report)
    assert type(redacted) is type(report)
    assert redacted.target_name == "[REDACTED]"
    assert redacted.raw_output == "[REDACTED]"
    assert redacted.results[0].description == "[REDACTED]"
    assert redacted.results[0].status is InsoStatus.FAIL
    assert report.results[0].description == "private"


def test_recursion_covers_nested_public_fields_and_preserves_schema_keys():
    class Status(str, Enum):
        OK = "ok"

    class Report(BaseModel):
        details: list[dict] = Field(default_factory=list)
        status: Status = Status.OK

    report = Report(details=[{"private": ["private", None, 3, ("private",)]}])
    copy = Redactor(["private", "ok"]).redact_report(report)
    assert copy.details == [{"[REDACTED]": ["[REDACTED]", None, 3, ("[REDACTED]",)]}]
    assert copy.status is Status.OK
    assert report.details[0]["private"][0] == "private"


def test_header_dictionary_credentials_are_redacted_without_known_values():
    class Report(BaseModel):
        headers: dict[str, str]

    report = Report(headers={"Authorization": "private", "X-Request-ID": "request"})
    copy = Redactor().redact_report(report)
    assert copy.headers == {"Authorization": "[REDACTED]", "X-Request-ID": "request"}


def test_literal_schema_discriminators_are_not_corrupted_by_known_values():
    from typing import Literal

    class Report(BaseModel):
        source: Literal["native", "tap"] = "native"
        message: str

    report = Report(message="native")
    copy = Redactor(["native"]).redact_report(report)
    assert copy.source == "native"
    assert copy.message == "[REDACTED]"
    assert Report.model_validate_json(copy.model_dump_json()) == copy


def test_workflow_masks_escape_command_injection_and_ignore_empty_values():
    value = "first%\r\n::error::injected"
    assert escape_workflow_command(value) == "first%25%0D%0A::error::injected"
    assert mask_commands([value, "", value]) == [
        "::add-mask::first%25%0D%0A::error::injected"
    ]


def test_known_url_secret_is_matched_before_credential_pattern_changes():
    value = "https://example.test/resource?token=token-value&customer=private-customer"
    assert Redactor([value]).redact(value) == "[REDACTED]"


def test_known_value_inside_a_credential_key_does_not_disable_redaction():
    value = Redactor(env_vars=["MODE=api"]).redact("api_key=private-credential")
    assert "private-credential" not in value


def test_overlapping_known_values_are_fully_redacted():
    redactor = Redactor(["prefix-shared", "shared-PRIVATE_TAIL"])
    assert redactor.redact("prefix-shared-PRIVATE_TAIL") == "[REDACTED]"


def test_known_value_containing_a_redaction_marker_is_still_hidden():
    value = "prefix-[REDACTED]-private"
    assert Redactor([value]).redact(value) == "[REDACTED]"


def test_partial_marker_overlap_does_not_corrupt_replacement_markers():
    redactor = Redactor(["R", "TED]-private"])
    once = redactor.redact("[REDACTED]-private")
    assert once == "[REDACTED]"
    assert redactor.redact(once) == once


def test_repeated_redaction_preserves_adjacent_assertion_details():
    redactor = Redactor()
    once = redactor.redact('{"token":"private"}ACTUAL=one EXPECTED=two')
    assert "private" not in once
    assert redactor.redact(once) == once
    assert "ACTUAL=one EXPECTED=two" in once


def test_native_surrogate_strings_become_publishable_unicode():
    report = InsoRunReport(
        plan_end=1,
        results=[
            InsoResult(
                id=1,
                status=InsoStatus.FAIL,
                description="invalid \ud800",
                message="reason \udfff",
            )
        ],
    )
    sanitized = Redactor().redact_report(report)
    assert sanitized.results[0].description == "invalid \ufffd"
    assert sanitized.results[0].message == "reason \ufffd"
    assert (
        json.loads(sanitized.model_dump_json())["results"][0]["description"]
        == "invalid \ufffd"
    )
