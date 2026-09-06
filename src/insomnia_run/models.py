from enum import Enum

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
    message: str | None = None


class InsoRunReport(BaseModel):
    run_type: RunType = RunType.COLLECTION
    target_name: str | None = None
    raw_output: str | None = None
    tap_version: int = 13
    plan_start: int = 1
    plan_end: int
    results: list[InsoResult] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)

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


class _CommonOptions(BaseModel):
    working_dir: str
    identifier: str | None = None
    environment: str | None = None
    request_timeout: int | None = Field(default=None, gt=0)
    bail: bool = False
    disable_cert_validation: bool = False
    https_proxy: str | None = None
    http_proxy: str | None = None
    no_proxy: str | None = None
    data_folders: list[str] | None = None
    verbose: bool = False
    execution_timeout: int = Field(default=300, gt=0)


class InsoCollectionOptions(_CommonOptions):
    request_name_pattern: str | None = None
    item: list[str] | None = None
    globals: str | None = None
    delay_request: int | None = Field(default=None, gt=0)
    env_var: dict[str, str] | None = None
    iteration_count: int | None = Field(default=None, gt=0)
    iteration_data: str | None = None


class InsoTestOptions(_CommonOptions):
    test_name_pattern: str | None = None
    keep_file: bool = False
