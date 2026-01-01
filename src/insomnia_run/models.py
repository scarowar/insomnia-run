from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class TestStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"

class TestResult(BaseModel):
    id: int
    status: TestStatus
    description: str

class TestRunReport(BaseModel):
    tap_version: int = 13
    plan_start: int = 1
    plan_end: int
    results: List[TestResult] = Field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.PASS)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.FAIL)

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.status == TestStatus.SKIP)

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed_count / self.total_tests) * 100.0
