"""Project Inso's private collection report onto the public report contract."""

import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import InsoResult, InsoRunReport, InsoStatus, RequestExecution, RunError


class _NativeModel(BaseModel):
    model_config = ConfigDict(strict=True)


class _Test(_NativeModel):
    testCase: str
    status: str
    executionTime: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    errorMessage: str | None = None


class _Response(_NativeModel):
    status: str | None = None
    code: int | None = None
    responseTime: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class _Execution(_NativeModel):
    request: dict
    response: _Response | None = None
    tests: list[_Test]
    iteration: int | None = Field(default=None, ge=0)


class _Report(_NativeModel):
    executions: list[_Execution]
    error: str | None = None


_CREDENTIAL_HEADER = re.compile(
    r"auth|cookie|token|secret|passw|credential|api[-_]?key|csrf|xsrf|bearer|basic|session|jwt",
    re.I,
)


def validate_capture_headers(names: list[str]) -> list[str]:
    result = []
    for name in names:
        name = name.strip().lower()
        if not re.fullmatch(
            r"[a-z0-9!#$%&'+.^_`|~-]{1,128}", name
        ) or _CREDENTIAL_HEADER.search(name):
            raise ValueError(
                "Response header names must be explicit and non-credential-bearing."
            )
        if name not in result:
            result.append(name)
    return result


def _seconds(milliseconds: float | None) -> float | None:
    return milliseconds / 1000 if milliseconds is not None else None


def parse_native_report(
    payload: str, *, capture_headers: list[str] | None = None
) -> InsoRunReport:
    headers = validate_capture_headers(capture_headers or [])
    try:
        data = json.loads(payload)
        native = _Report.model_validate(data)
        report = InsoRunReport(plan_end=0, source="native")
        statuses = {
            "passed": InsoStatus.PASS,
            "failed": InsoStatus.FAIL,
            "skipped": InsoStatus.SKIP,
        }
        for occurrence, execution in enumerate(native.executions, 1):
            request = execution.request
            if not isinstance(request.get("name"), str) or not isinstance(
                request.get("_id"), str
            ):
                raise ValueError("Invalid request identity.")
            response = execution.response
            selected_headers: dict[str, str] = {}
            if headers and response is not None:
                raw_headers = (
                    data["executions"][occurrence - 1]
                    .get("response", {})
                    .get("headers", {})
                )
                if isinstance(raw_headers, dict):
                    for name, value in raw_headers.items():
                        if isinstance(name, str) and isinstance(value, str):
                            key = name.lower()
                            if (
                                key in headers
                                and len(value.encode("utf-8", errors="replace")) <= 2048
                            ):
                                selected_headers[key] = value
            report.executions.append(
                RequestExecution(
                    id=occurrence,
                    request_id=request["_id"],
                    name=request["name"],
                    iteration=execution.iteration,
                    status_code=response.code if response else None,
                    status=response.status if response else None,
                    duration_seconds=_seconds(response.responseTime)
                    if response
                    else None,
                    headers=selected_headers,
                )
            )
            for test in execution.tests:
                report.results.append(
                    InsoResult(
                        id=len(report.results) + 1,
                        status=statuses[test.status],
                        description=test.testCase,
                        message=test.errorMessage,
                        duration_seconds=_seconds(test.executionTime),
                        execution_id=occurrence,
                    )
                )
        report.plan_end = len(report.results)
        if native.error:
            report.complete = False
            report.run_error = RunError(kind="execution", message=native.error)
        return report
    except (ValidationError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid native Inso report.") from error
