import re

from .models import InsoResult, InsoRunReport, InsoStatus


class TapParser:
    VERSION = r"^TAP version (\d+)$"
    PLAN = r"^(\d+)\.\.(\d+)(?:\s+#.*)?$"
    TEST_LINE = r"^(ok|not ok)\s+(\d+)(?:\s+(?:-\s+)?(.*))?$"
    SKIP_DIRECTIVE = r"#\s*SKIP(?:\s|$)"
    BAILOUT = r"^Bail out!"

    def parse(self, output: str, *, require_tap: bool = False) -> InsoRunReport:
        report = InsoRunReport(plan_end=0)
        planned_tests = 0
        block_plan = None
        block_count = 0
        block_active = False
        saw_plan = False
        invalid_tap = False
        bailed_out = False

        def finish_block():
            nonlocal block_plan, block_count, block_active, invalid_tap
            if block_active and (block_plan is None or block_count != block_plan):
                invalid_tap = True
            block_plan = None
            block_count = 0
            block_active = False

        lines = output.strip().split("\n")
        for line in lines:
            line = line.strip()

            if re.search(self.BAILOUT, line, re.IGNORECASE):
                bailed_out = True
                break

            match = re.search(self.VERSION, line)
            if match:
                finish_block()
                block_active = True
                report.tap_version = int(match.group(1))
                continue

            match = re.search(self.PLAN, line)
            if match:
                if block_plan is not None:
                    finish_block()
                start, end = int(match.group(1)), int(match.group(2))
                if start != 1:
                    invalid_tap = True
                block_plan = max(0, end - start + 1)
                planned_tests += block_plan
                block_active = saw_plan = True
                # Legacy test suites put the plan after their assertion lines.
                if block_count:
                    finish_block()
                continue

            match = re.search(self.TEST_LINE, line)
            if match:
                status_str = match.group(1)
                block_active = True
                block_count += 1
                if int(match.group(2)) != block_count:
                    invalid_tap = True
                # Collection requests each emit their own TAP plan and restart IDs.
                test_id = len(report.results) + 1
                description = match.group(3) or ""

                # Check for SKIP directive in description
                if re.search(self.SKIP_DIRECTIVE, description, re.IGNORECASE):
                    status = InsoStatus.SKIP
                elif status_str == "ok":
                    status = InsoStatus.PASS
                else:
                    status = InsoStatus.FAIL

                result = InsoResult(id=test_id, status=status, description=description)
                report.results.append(result)

        finish_block()
        if bailed_out or invalid_tap or (require_tap and not saw_plan):
            report.results.append(
                InsoResult(
                    id=len(report.results) + 1,
                    status=InsoStatus.FAIL,
                    description=(
                        "Inso CLI Error: TAP bailout."
                        if bailed_out
                        else "Inso CLI Error: Missing or incomplete TAP output."
                    ),
                )
            )
        report.plan_end = max(planned_tests, len(report.results))
        return report
