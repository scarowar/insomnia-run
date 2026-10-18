import re
from dataclasses import dataclass, field

from .models import InsoResult, InsoRunReport, InsoStatus, RunError


@dataclass
class _TapState:
    report: InsoRunReport = field(default_factory=lambda: InsoRunReport(plan_end=0))
    planned_tests: int = 0
    block_plan: int | None = None
    block_count: int = 0
    block_active: bool = False
    saw_plan: bool = False
    invalid_tap: bool = False

    def finish_block(self) -> None:
        if self.block_active and (
            self.block_plan is None or self.block_count != self.block_plan
        ):
            self.invalid_tap = True
        self.block_plan = None
        self.block_count = 0
        self.block_active = False

    def start_version(self, version: int) -> None:
        self.finish_block()
        self.block_active = True
        self.report.tap_version = version

    def add_plan(self, start: int, end: int) -> None:
        if self.block_plan is not None:
            self.finish_block()
        if start != 1:
            self.invalid_tap = True
        self.block_plan = max(0, end - start + 1)
        self.planned_tests += self.block_plan
        self.block_active = self.saw_plan = True
        # Legacy test suites put the plan after their assertion lines.
        if self.block_count:
            self.finish_block()

    def add_result(self, source_id: int, result: InsoResult) -> None:
        self.block_active = True
        self.block_count += 1
        if source_id != self.block_count:
            self.invalid_tap = True
        self.report.results.append(result)

    def finish(self, *, require_tap: bool, bailed_out: bool) -> InsoRunReport:
        self.finish_block()
        if bailed_out or self.invalid_tap or (require_tap and not self.saw_plan):
            self.report.complete = False
            self.report.run_error = RunError(
                kind="protocol",
                message=(
                    "Inso CLI Error: TAP bailout."
                    if bailed_out
                    else "Inso CLI Error: Missing or incomplete TAP output."
                ),
            )
        self.report.plan_end = max(self.planned_tests, len(self.report.results))
        return self.report


@dataclass
class _TapDiagnostics:
    previous: InsoResult | None = None
    lines: list[str] | None = None
    indent: str = ""

    def consume(self, raw_line: str) -> bool:
        if self.lines is not None:
            if raw_line == self.indent + "...":
                if self.previous is not None:
                    self.previous.message = "\n".join(self.lines)
                self.lines = None
                self.previous = None
                return True
            if raw_line.startswith(self.indent):
                self.lines.append(raw_line[len(self.indent) :])
                return True
            self.lines = None
            self.previous = None
        start = re.fullmatch(r"([ \t]+)---", raw_line)
        if (
            start
            and self.previous is not None
            and self.previous.status == InsoStatus.FAIL
        ):
            self.indent, self.lines = start[1], []
            return True
        self.previous = None
        return False


class TapParser:
    VERSION = r"^TAP version (\d+)$"
    PLAN = r"^(\d+)\.\.(\d+)(?:\s+#.*)?$"
    TEST_LINE = r"^(ok|not ok)\s+(\d+)(?:\s+(?:-\s+)?(.*))?$"
    SKIP_DIRECTIVE = r"#\s*SKIP(?:\s|$)"
    BAILOUT = r"^Bail out!"

    def _result(self, match: re.Match[str], result_id: int) -> InsoResult:
        description = match.group(3) or ""
        if re.search(self.SKIP_DIRECTIVE, description, re.IGNORECASE):
            status = InsoStatus.SKIP
        elif match.group(1) == "ok":
            status = InsoStatus.PASS
        else:
            status = InsoStatus.FAIL
        return InsoResult(id=result_id, status=status, description=description)

    def parse(self, output: str, *, require_tap: bool = False) -> InsoRunReport:
        state = _TapState()
        bailed_out = False
        diagnostics = _TapDiagnostics()
        for raw_line in output.splitlines():
            if diagnostics.consume(raw_line):
                continue
            line = raw_line.strip()

            if re.search(self.BAILOUT, line, re.IGNORECASE):
                bailed_out = True
                break

            match = re.search(self.VERSION, line)
            if match:
                state.start_version(int(match.group(1)))
                continue

            match = re.search(self.PLAN, line)
            if match:
                state.add_plan(int(match.group(1)), int(match.group(2)))
                continue

            match = re.search(self.TEST_LINE, line)
            if match:
                # Collection requests each emit their own TAP plan and restart IDs.
                result = self._result(match, len(state.report.results) + 1)
                state.add_result(int(match.group(2)), result)
                diagnostics.previous = result

        return state.finish(require_tap=require_tap, bailed_out=bailed_out)
