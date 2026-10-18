from enum import Enum
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class RunType(str, Enum):
    COLLECTION = "collection"
    TEST = "test"


class InsoStatus(str, Enum):
    # TAP status value, not a credential.
    PASS = "PASS"  # nosec B105
    FAIL = "FAIL"
    SKIP = "SKIP"


class InsoResult(BaseModel):
    id: int
    status: InsoStatus
    description: str
    message: Optional[str] = None
    duration_seconds: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    execution_id: Optional[int] = None


class RequestExecution(BaseModel):
    id: int
    request_id: Optional[str] = None
    name: str
    iteration: Optional[int] = Field(default=None, ge=0)
    status_code: Optional[int] = None
    status: Optional[str] = None
    duration_seconds: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    headers: dict[str, str] = Field(default_factory=dict)


class RunError(BaseModel):
    kind: Literal["execution", "timeout", "protocol"]
    message: str


class InsoRunReport(BaseModel):
    schema_version: Literal[1] = 1
    run_type: RunType = RunType.COLLECTION
    target_name: Optional[str] = None
    raw_output: Optional[str] = None
    tap_version: int = 13
    plan_start: int = 1
    plan_end: int
    results: List[InsoResult] = Field(default_factory=list)
    executions: List[RequestExecution] = Field(default_factory=list)
    source: Literal["native", "tap"] = "tap"
    complete: bool = True
    run_error: Optional[RunError] = None

    @property
    def request_count(self) -> Optional[int]:
        return len(self.executions) if self.source == "native" else None

    @property
    def exit_code(self) -> int:
        return 3 if self.run_error else (1 if self.failed_count else 0)

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
    delay_request: Optional[int] = Field(default=None, ge=0)
    request_timeout: Optional[int] = Field(default=None, ge=0)
    env_var: Optional[list[str] | dict[str, str]] = None
    iteration_count: Optional[int] = Field(default=None, gt=0)
    iteration_data: Optional[str] = None
    bail: bool = False
    disable_cert_validation: bool = False
    https_proxy: Optional[str] = None
    http_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    data_folders: Optional[List[str]] = None
    verbose: bool = False
    execution_timeout: int = Field(default=300, gt=0)
    capture_response_headers: list[str] = Field(default_factory=list)


class InsoTestOptions(BaseModel):
    working_dir: str
    identifier: Optional[str] = None
    environment: Optional[str] = None
    test_name_pattern: Optional[str] = None
    bail: bool = False
    keep_file: bool = False
    request_timeout: Optional[int] = Field(default=None, ge=0)
    disable_cert_validation: bool = False
    https_proxy: Optional[str] = None
    http_proxy: Optional[str] = None
    no_proxy: Optional[str] = None
    data_folders: Optional[List[str]] = None
    verbose: bool = False
    execution_timeout: int = Field(default=300, gt=0)
