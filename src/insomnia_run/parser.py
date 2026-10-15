import re

from .models import InsoResult, InsoRunReport, InsoStatus


class TapParser:
    VERSION = r"^TAP version (\d+)$"
    PLAN = r"^(\d+)\.\.(\d+)$"
    TEST_LINE = r"^(ok|not ok)\s+(\d+)\s+(?:-\s+)?(.*)$"
    SKIP_DIRECTIVE = r"#\s*SKIP"

    def parse(self, output: str) -> InsoRunReport:
        report = InsoRunReport(plan_end=0)
        planned_tests = 0

        lines = output.strip().split("\n")
        for line in lines:
            line = line.strip()

            match = re.search(self.VERSION, line)
            if match:
                report.tap_version = int(match.group(1))
                continue

            match = re.search(self.PLAN, line)
            if match:
                planned_tests += max(0, int(match.group(2)) - int(match.group(1)) + 1)
                continue

            match = re.search(self.TEST_LINE, line)
            if match:
                status_str = match.group(1)
                # Collection requests each emit their own TAP plan and restart IDs.
                test_id = len(report.results) + 1
                description = match.group(3)

                # Check for SKIP directive in description
                if re.search(self.SKIP_DIRECTIVE, description, re.IGNORECASE):
                    status = InsoStatus.SKIP
                elif status_str == "ok":
                    status = InsoStatus.PASS
                else:
                    status = InsoStatus.FAIL

                result = InsoResult(id=test_id, status=status, description=description)
                report.results.append(result)

        report.plan_end = max(planned_tests, len(report.results))
        return report
