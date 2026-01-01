import re
from .models import TestResult, TestStatus, TestRunReport


class TapParser:
    def __init__(self):
        self.state = "searching"

    VERSION = "^TAP version (\d+)$"
    PLAN = "^(\d+)\.\.(\d+)$"
    TEST_LINE = "^(ok|not ok)\s+(\d+)\s+(?:-\s+)?(.*)$"

    def parse(self, output: str) -> TestRunReport:
        report = TestRunReport(plan_end=0)

        lines = output.strip().split('\n')
        for line in lines:
            line = line.strip()

            match = re.search(self.VERSION, line)
            if match:
                self.state = "parsing"
                report.tap_version = int(match.group(1))
                continue

            if self.state != "parsing":
                continue

            match = re.search(self.PLAN, line)
            if match:
                report.plan_start = int(match.group(1))
                report.plan_end = int(match.group(2))
                continue

            match = re.search(self.TEST_LINE, line)
            if match:
                status_str = match.group(1)
                test_id = int(match.group(2))
                description = match.group(3)

                status = TestStatus.PASS if status_str == "ok" else TestStatus.FAIL

                result = TestResult(id=test_id, status=status, description=description)
                report.results.append(result)

        return report
