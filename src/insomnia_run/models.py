from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RunType(str, Enum):
    COLLECTION = "collection"
    TEST = "test"


class InsoStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


class InsoResult(BaseModel):
    id: int
    status: InsoStatus
    description: str


class InsoRunReport(BaseModel):
    run_type: RunType = RunType.COLLECTION
    target_name: Optional[str] = None
    raw_output: Optional[str] = None
    tap_version: int = 13
    plan_start: int = 1
    plan_end: int
    results: List[InsoResult] = Field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.status == InsoStatus.PASS)

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == InsoStatus.FAIL)

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.status == InsoStatus.SKIP)

    @property
    def total_tests(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return (self.passed_count / self.total_tests) * 100.0


class InsoCollectionOptions(BaseModel):
    working_dir: str
    identifier: Optional[str] = None
    environment: Optional[str] = None
    request_name_pattern: Optional[str] = None
    item: Optional[List[str]] = None
    globals: Optional[str] = None
    delay_request: Optional[int] = None
    request_timeout: Optional[int] = None
    env_var: Optional[dict[str, str]] = None
    iteration_count: Optional[int] = None
    iteration_data: Optional[str] = None
    bail: bool = False
    disable_cert_validation: bool = False
    https_proxy: Optional[str] = None
    http_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    data_folders: Optional[List[str]] = None
    verbose: bool = False
    execution_timeout: int = 300


class InsoTestOptions(BaseModel):
    working_dir: str
    identifier: Optional[str] = None
    environment: Optional[str] = None
    test_name_pattern: Optional[str] = None
    bail: bool = False
    keep_file: bool = False
    request_timeout: Optional[int] = None
    disable_cert_validation: bool = False
    https_proxy: Optional[str] = None
    http_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    data_folders: Optional[List[str]] = None
    verbose: bool = False
    execution_timeout: int = 300
