"""Best-effort publication redaction; this is not a secret-detection guarantee."""

import base64
import html
import json
import re
from bisect import bisect_right
from collections.abc import Iterable, Mapping
from enum import Enum
from typing import Literal, TypeVar, get_origin
from urllib.parse import parse_qsl, quote, quote_plus, unquote, unquote_plus

from pydantic import BaseModel

_Model = TypeVar("_Model", bound=BaseModel)
_REDACTED = "[REDACTED]"
_CREDENTIAL_NAME = (
    r"(?:authorization|proxy-authorization|cookie|set-cookie|"
    r"x-api-key|api[_-]?key|access[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?secret|password|passwd|secret|token|"
    r"x-amz-signature|x-amz-credential|signature|sig)"
)
_HEADER = re.compile(
    r"(?im)(\b(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)"
    r"\s*:\s*)([^\r\n]+)"
)
_ASSIGNMENT = re.compile(
    rf"(?i)([\"']?(?<![A-Za-z0-9])(?:[A-Za-z0-9]{{1,32}}[_-]){{0,4}}"
    rf"{_CREDENTIAL_NAME}[\"']?\s*[:=]\s*)"
)
_ASSIGNMENT_VALUE = re.compile(r"""[^\s&,;<>"']{1,16384}""")
_URL_USERINFO = re.compile(r"(?i)(\b[a-z][a-z0-9+.-]{0,31}://)[^\s/@<>\"']{1,1024}@")
_QUERY_VALUE = re.compile(r"([?&])([^\s?&#=<>\"']+)=([^\s&#<>\"']*)")
_QUERY_CREDENTIAL = re.compile(rf"(?i)^{_CREDENTIAL_NAME}$")
_ENV_CREDENTIAL = re.compile(
    rf"(?i)^(?:[A-Za-z0-9]{{1,32}}[_-]){{0,4}}{_CREDENTIAL_NAME}$"
)


def _quoted_assignment_end(text: str, start: int) -> int:
    quote = text[start]
    end = text.find(quote, start + 1)
    while end != -1:
        preceding = end - 1
        while preceding > start and text[preceding] == "\\":
            preceding -= 1
        if (end - preceding - 1) % 2 == 0:
            return end
        end = text.find(quote, end + 1)
    return len(text)


def _assignment_value_span(text: str, start: int) -> tuple[int, int] | None:
    if start < len(text) and text[start] in ('"', "'"):
        return start + 1, _quoted_assignment_end(text, start)
    end = start
    while match := _ASSIGNMENT_VALUE.match(text, end):
        end = match.end()
    return (start, end) if end > start else None


def _variants(value: str) -> set[str]:
    decoded = {value, unquote(value), unquote_plus(value)}
    try:
        raw = base64.b64decode(value, altchars=b"-_", validate=True)
        plain = raw.decode("utf-8")
        if len(value) >= 8 and plain.isprintable():
            decoded.add(plain)
    except ValueError:
        pass
    variants = set(decoded)
    for plain in decoded:
        variants.update(
            {
                quote(plain, safe=""),
                quote(plain),
                quote_plus(plain, safe=""),
                json.dumps(plain)[1:-1],
                html.escape(plain),
                base64.b64encode(plain.encode()).decode(),
                base64.urlsafe_b64encode(plain.encode()).decode(),
            }
        )
    variants.update(
        re.sub(r"%[0-9A-F]{2}", lambda match: match[0].lower(), item)
        for item in tuple(variants)
    )
    return variants - {""}


class Redactor:
    def __init__(
        self,
        values: Iterable[str] = (),
        env_vars: Iterable[str] | Mapping[str, str] | None = None,
    ) -> None:
        secrets = list(values)
        pairs: Iterable[tuple[str, str]]
        if isinstance(env_vars, Mapping):
            pairs = env_vars.items()
        elif env_vars is not None:
            pairs = [
                pair
                for item in env_vars
                for pair in parse_qsl(item, keep_blank_values=True)
            ]
        else:
            pairs = []
        secrets.extend(
            value
            for key, value in pairs
            if _ENV_CREDENTIAL.fullmatch(key) or len(value) >= 8
        )
        self.values = tuple(dict.fromkeys(value for value in secrets if value))
        variants = {variant for value in self.values for variant in _variants(value)}
        self._known = (
            re.compile(
                "(?=("
                + "|".join(
                    re.escape(value)
                    for value in sorted(variants, key=len, reverse=True)
                )
                + "))"
            )
            if variants
            else None
        )

    def redact(self, text: str) -> str:
        text = re.sub(r"[\uD800-\uDFFF]", "\ufffd", text)
        # Find every sensitive span in the original text so one rule cannot hide another.
        spans = self._known_spans(text)
        spans.extend(
            (match.end(1), match.end() - 1) for match in _URL_USERINFO.finditer(text)
        )
        spans.extend(
            match.span(3)
            for match in _QUERY_VALUE.finditer(text)
            if _QUERY_CREDENTIAL.fullmatch(unquote_plus(match[2]))
        )
        spans.extend(match.span(2) for match in _HEADER.finditer(text))
        assignment_end = 0
        for match in _ASSIGNMENT.finditer(text):
            if match.start() < assignment_end:
                continue
            span = _assignment_value_span(text, match.end())
            if span is not None:
                spans.append(span)
                assignment_end = span[1]
        return _replace_spans(text, spans)

    def _known_spans(self, text: str) -> list[tuple[int, int]]:
        if self._known is None:
            return []
        markers = [match.span() for match in re.finditer(re.escape(_REDACTED), text)]
        starts = [start for start, _ in markers]
        spans: list[tuple[int, int]] = []
        for match in self._known.finditer(text):
            start, end = match.span(1)
            marker = bisect_right(starts, start) - 1
            if marker >= 0 and end <= markers[marker][1]:
                continue
            if marker >= 0 and start < markers[marker][1]:
                start = markers[marker][0]
            last = bisect_right(starts, end) - 1
            if last >= 0 and markers[last][0] < end < markers[last][1]:
                end = markers[last][1]
            spans.append((start, end))
        return spans

    def redact_report(self, report: _Model) -> _Model:
        copy = report.model_copy(deep=True)
        self._redact_model(copy)
        return copy

    def _redact_model(self, model: BaseModel) -> None:
        for name, field in type(model).model_fields.items():
            if get_origin(field.annotation) is not Literal:
                setattr(model, name, self._redact_value(getattr(model, name)))

    def _redact_value(self, value: object) -> object:
        if isinstance(value, Enum):
            return value
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, BaseModel):
            self._redact_model(value)
        elif isinstance(value, dict):
            return {
                key: (
                    _REDACTED
                    if isinstance(key, str) and _QUERY_CREDENTIAL.fullmatch(key)
                    else self._redact_value(item)
                )
                for key, item in value.items()
            }
        elif isinstance(value, list):
            return [self._redact_value(item) for item in value]
        elif isinstance(value, tuple):
            return tuple(self._redact_value(item) for item in value)
        return value


def _replace_spans(text: str, spans: list[tuple[int, int]]) -> str:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    output: list[str] = []
    cursor = 0
    for start, end in merged:
        output.extend((text[cursor:start], _REDACTED))
        cursor = end
    output.append(text[cursor:])
    return "".join(output)


def escape_workflow_command(value: str) -> str:
    """Escape command data, not the separate annotation property syntax."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def mask_commands(values: Iterable[str]) -> list[str]:
    return [
        "::add-mask::" + escape_workflow_command(value)
        for value in dict.fromkeys(values)
        if value
    ]
