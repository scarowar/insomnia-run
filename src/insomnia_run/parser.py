import re

from .models import InsoResult, InsoRunReport, InsoStatus, RunType

_VERSION_RE = re.compile(r"^TAP version (\d+)$")
_PLAN_RE = re.compile(r"^(\d+)\.\.(\d+)$")
_TEST_LINE_RE = re.compile(r"^(ok|not ok)\s+(\d+)\s+-?\s*(.*)$")
_SKIP_DIRECTIVE_RE = re.compile(r"#\s*SKIP\b", re.IGNORECASE)
_ERROR_LINE_RE = re.compile(r"^error:\s*(.+)$")


class TapParser:
    """Parse Inso CLI TAP output into a report.

    Inso emits two TAP dialects under one binary (verified against 13.2.0):
    ``run test`` uses Mocha's TAP-12 (plan last, no dash, failure detail as
    2-space-indented lines) and ``run collection`` uses a home-grown TAP-13
    with one document per request x iteration and failure detail only in a
    non-TAP ``error: ...`` footer. The dialect is selected by ``run_type``;
    the interface stays one call.
    """

    def parse(self, raw_output: str, run_type: RunType = RunType.COLLECTION) -> InsoRunReport:
        lines = raw_output.splitlines()
        if run_type == RunType.TEST:
            report = self._parse_mocha_tap12(lines)
        else:
            report = self._parse_inso_tap13(lines)

        declared = report.plan_end - report.plan_start + 1
        if report.plan_end and declared != report.total_tests:
            report.diagnostics.append(
                f"TAP plan declares {declared} results but {report.total_tests} were parsed; "
                "output may be truncated."
            )
        return report

    def _parse_mocha_tap12(self, lines: list[str]) -> InsoRunReport:
        report = InsoRunReport(plan_end=0, tap_version=12)

        i = 0
        while i < len(lines):
            line = lines[i]
            i += 1

            version = _VERSION_RE.match(line)
            if version:
                report.tap_version = int(version.group(1))
                continue

            plan = _PLAN_RE.match(line)
            if plan:
                report.plan_start = int(plan.group(1))
                report.plan_end = int(plan.group(2))
                continue

            test = _TEST_LINE_RE.match(line)
            if test:
                report.results.append(self._result(test.group(1), test.group(2), test.group(3)))
                if report.results[-1].status == InsoStatus.FAIL:
                    report.results[-1].message = self._mocha_detail(lines, i)

        return report

    @staticmethod
    def _mocha_detail(lines: list[str], start: int) -> str | None:
        """First 2-space-indented line after a failing test is the message.

        TAP-YAML blocks (a leading ``---``) are skipped so the message is the
        actual assertion text, not the block delimiter.
        """
        for line in lines[start:]:
            if not line.strip():
                continue
            if line.startswith("  "):
                stripped = line.strip()
                if stripped == "---":
                    continue
                return stripped
            break
        return None

    def _parse_inso_tap13(self, lines: list[str]) -> InsoRunReport:
        report = InsoRunReport(plan_end=0, tap_version=13)
        failing: list[InsoResult] = []
        errors: list[str] = []

        for line in lines:
            version = _VERSION_RE.match(line)
            if version:
                report.tap_version = int(version.group(1))
                continue

            plan = _PLAN_RE.match(line)
            if plan:
                # One document per request x iteration; numbering restarts,
                # so plans aggregate instead of overwriting.
                report.plan_end += int(plan.group(2))
                continue

            test = _TEST_LINE_RE.match(line)
            if test:
                result = self._result(test.group(1), test.group(2), test.group(3))
                result.id = len(report.results) + 1
                report.results.append(result)
                if result.status == InsoStatus.FAIL:
                    failing.append(result)
                continue

            error = _ERROR_LINE_RE.match(line)
            if error:
                errors.append(error.group(1).strip())

        self._pair_footer_errors(errors, failing, report)
        return report

    @staticmethod
    def _pair_footer_errors(
        errors: list[str], failing: list[InsoResult], report: InsoRunReport
    ) -> None:
        """Attach harvested footer errors to failing results in order.

        inso emits one footer error per failed test, so positional pairing is
        only trustworthy when the counts agree; otherwise attribution would be
        a guess and every error stays in diagnostics.
        """
        if len(errors) == len(failing):
            for error, result in zip(errors, failing):
                result.message = error
        else:
            report.diagnostics.extend(errors)

    @staticmethod
    def _result(status_str: str, test_id: str, description: str) -> InsoResult:
        skip = bool(_SKIP_DIRECTIVE_RE.search(description))
        description = _SKIP_DIRECTIVE_RE.sub("", description).strip()
        if skip:
            status = InsoStatus.SKIP
        elif status_str == "ok":
            status = InsoStatus.PASS
        else:
            status = InsoStatus.FAIL
        return InsoResult(id=int(test_id), status=status, description=description)
