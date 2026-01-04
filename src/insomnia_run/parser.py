import re

from .models import InsoResult, InsoRunReport, InsoStatus


class TapParser:
    VERSION = r"^TAP version (\d+)$"
    PLAN = r"^(\d+)\.\.(\d+)$"
    TEST_LINE = r"^(ok|not ok)\s+(\d+)\s+(?:-\s+)?(.*)$"
    SKIP_DIRECTIVE = r"#\s*SKIP"

    def parse(self, output: str) -> InsoRunReport:
        report = InsoRunReport(plan_end=0)

        lines = output.strip().split("\n")
        for line in lines:
            line = line.strip()

            match = re.search(self.VERSION, line)
            if match:
                report.tap_version = int(match.group(1))
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

                # Check for SKIP directive in description
                if re.search(self.SKIP_DIRECTIVE, description, re.IGNORECASE):
                    status = InsoStatus.SKIP
                elif status_str == "ok":
                    status = InsoStatus.PASS
                else:
                    status = InsoStatus.FAIL

                result = InsoResult(id=test_id, status=status, description=description)
                report.results.append(result)

        return report
