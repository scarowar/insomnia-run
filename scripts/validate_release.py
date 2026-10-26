"""Run the installed-wheel release suite and retain inspectable report evidence."""

import argparse
from collections import Counter
from importlib.metadata import version
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import subprocess  # nosec B404 # fixed local test and GitHub-renderer commands
import sys
import tempfile
import tomllib
from xml.etree import ElementTree  # nosec B405 # locally generated pytest XML only


class RenderedReport(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[str] = []
        self.assertions: list[str] = []
        self.tags: list[str] = []
        self.capture: str | None = None
        self.capture_tag = "code"
        self.text: list[str] = []
        self.unsafe_tags: set[str] = set()
        self.table_headers: list[str] = []
        self.header_text: list[str] = []
        self.column = 0
        self.nested_disclosures = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"img", "script", "iframe", "h1"}:
            self.unsafe_tags.add(tag)
        if tag == "details" and "details" in self.tags:
            self.nested_disclosures = True
        if tag == "table":
            self.table_headers = []
        if tag == "tr":
            self.column = 0
        if tag == "th":
            self.header_text = []
        if tag == "td":
            self.column += 1
            if self.column == 2 and self.table_headers == [
                "Request",
                "Assertion",
                "Failure",
            ]:
                self.capture = "assertion"
                self.capture_tag = "td"
                self.text = []
        if tag == "code":
            self._start_code()
        if tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self.tags.append(tag)

    def _start_code(self) -> None:
        self.capture = None
        self.capture_tag = "code"
        if (
            "td" in self.tags
            and self.column == 1
            and self.table_headers
            == ["Request", "Passed", "Failed", "Skipped", "Response"]
        ):
            self.capture = "request"
        elif "strong" in self.tags and "li" in self.tags:
            self.capture = "assertion"
        self.text = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.text.append(data)
        if "th" in self.tags:
            self.header_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "th":
            self.table_headers.append("".join(self.header_text).strip())
        if tag == self.capture_tag and self.capture:
            target = self.requests if self.capture == "request" else self.assertions
            target.append("".join(self.text))
            self.capture = None
        if tag in self.tags:
            index = len(self.tags) - 1 - self.tags[::-1].index(tag)
            del self.tags[index:]


def require_installed_wheel(root: Path) -> None:
    import insomnia_run

    location = Path(insomnia_run.__file__).resolve()
    if location.is_relative_to(root / "src"):
        raise ValueError("Release validation must import the installed wheel.")
    expected = tomllib.loads((root / "pyproject.toml").read_text())["project"][
        "version"
    ]
    if version("insomnia-run") != expected:
        raise ValueError("Installed wheel version differs from the candidate.")
    source = root / "src" / "insomnia_run"
    installed = location.parent
    expected_files = {path.relative_to(source) for path in source.rglob("*.py")}
    installed_files = {path.relative_to(installed) for path in installed.rglob("*.py")}
    if expected_files != installed_files or any(
        (source / name).read_bytes() != (installed / name).read_bytes()
        for name in expected_files
    ):
        raise ValueError("Installed wheel source differs from the candidate.")


def require_unskipped_tests(path: Path) -> int:
    tree = ElementTree.parse(path)  # nosec B314 # emitted by this invocation of pytest
    suites = list(tree.iter("testsuite"))
    count = sum(int(suite.get("tests", "0")) for suite in suites)
    if not count or any(
        int(suite.get(attribute, "0"))
        for suite in suites
        for attribute in ("skipped", "failures", "errors")
    ):
        raise ValueError("Release tests must execute successfully without skips.")
    classes = {case.get("classname", "") for case in tree.iter("testcase")}
    for required in (
        "test_patch_regressions",
        "test_reporting_experience",
        "test_inso_compatibility",
        "test_native_compatibility",
        "test_managed_python",
        "test_release_tools",
    ):
        if not any(required in name.split(".") for name in classes):
            raise ValueError(f"Release suite did not execute {required}.")
    return count


def render_gfm(markdown: str) -> str:
    result = subprocess.run(  # nosec B603, B607 # fixed gh endpoint; content supplied on stdin
        ["gh", "api", "--method", "POST", "markdown", "--input", "-"],
        input=json.dumps({"text": markdown, "mode": "gfm"}),
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout


def _acceptance_report(label: str, counts: tuple[int, ...]):
    from insomnia_run.models import (
        InsoResult,
        InsoRunReport,
        InsoStatus,
        RequestExecution,
    )
    from insomnia_run.privacy import Redactor

    results: list[InsoResult] = []
    for execution, count in enumerate(counts, 1):
        for number in range(count):
            results.append(
                InsoResult(
                    id=len(results) + 1,
                    execution_id=execution,
                    status=InsoStatus.FAIL
                    if label == "mixed" and execution == 1 and number < 2
                    else InsoStatus.PASS,
                    description=f"check-{execution}-{number}",
                    message="error: Error: synthetic&credential+value | ACTUAL: undefined | EXPECTED: undefined"
                    if label == "mixed" and number == 0
                    else None,
                )
            )
    report = InsoRunReport(
        source="native",
        plan_end=len(results),
        results=results,
        executions=[
            RequestExecution(id=i, name=f"request-{i}", status_code=200, status="OK")
            for i in range(1, len(counts) + 1)
        ],
    )
    if label == "hostile":
        report.executions[0].name = "POST /<probe>&` @ghost #1"
        report.results[0].status = InsoStatus.FAIL
        report.results[0].description = "literal <img src=x> `ticks` & @ghost #1"
        report.results[
            0
        ].message = "literal | ![image](https://example.invalid) @ghost #1\n<details>full diagnostic</details>"
        report.raw_output = (
            "</details><img src=x><script>bad</script>\nsynthetic&credential+value\n"
            + "```" * 3000
        )
    return Redactor(values=["synthetic&credential+value"]).redact_report(report)


def _require_rendered_identities(report, html: str) -> None:
    rendered = RenderedReport()
    rendered.feed(html)
    if rendered.unsafe_tags:
        raise ValueError("Report content escaped its literal rendering.")
    if Counter(request.name for request in report.executions) != Counter(
        rendered.requests
    ):
        raise ValueError("Rendered report lost an executed request that fits.")
    if rendered.nested_disclosures:
        raise ValueError("Rendered report contains nested disclosures.")
    if Counter(result.description for result in report.results) != Counter(
        rendered.assertions
    ):
        raise ValueError("Rendered report assertion identities differ.")


def validate_reports(output: Path) -> None:
    from insomnia_run.reporter import Reporter

    output.mkdir(parents=True, exist_ok=True)
    reporter = Reporter()
    findings = []
    for label, counts in (
        ("mixed", (29, 10, 21, 1, 1)),
        ("scale", (1,) * 300),
        ("empty-requests", (0,) * 5),
        ("hostile", (2, 1, 0)),
    ):
        report = _acceptance_report(label, counts)
        markdown = reporter.generate_markdown(
            report, include_raw_output=label == "hostile"
        )
        junit = reporter.generate_junit(report)
        html = render_gfm(markdown)
        _require_rendered_identities(report, html)
        cases = list(ElementTree.fromstring(junit).iter("testcase"))  # nosec B314 # generated above
        if len(cases) != report.total_tests or len(markdown.encode("utf-8")) > 60_000:
            raise ValueError("Report evidence counts or Markdown size differ.")
        payload = report.model_dump_json(indent=2)
        if any(
            "synthetic&credential+value" in value
            for value in (payload, markdown, junit, html)
        ):
            raise ValueError("Synthetic credential survived publication redaction.")
        for suffix, contents in (
            ("json", payload),
            ("md", markdown),
            ("xml", junit),
            ("html", html),
        ):
            (output / f"{label}.{suffix}").write_text(contents, encoding="utf-8")
        findings.append(
            {
                "scenario": label,
                "requests": len(counts),
                "results": report.total_tests,
                "markdown_bytes": len(markdown.encode("utf-8")),
            }
        )
    (output / "report-checks.json").write_text(json.dumps(findings, indent=2) + "\n")


def validate(root: Path, output: Path) -> None:
    require_installed_wheel(root)
    output.mkdir(parents=True, exist_ok=True)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTEST_ADDOPTS"}
    }
    with tempfile.TemporaryDirectory(
        prefix="insomnia-release-tests-", dir=environment.get("RUNNER_TEMP")
    ) as scratch:
        subprocess.run(  # nosec B603 # fixed pytest arguments and caller-selected output directory
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--override-ini=addopts=",
                "--tb=short",
                "-rs",
                "--cov=insomnia_run",
                "--cov=scripts",
                "--cov-fail-under=95",
                f"--junitxml={output / 'tests.xml'}",
                "--basetemp",
                str(Path(scratch) / "cases"),
            ],
            cwd=root,
            env=environment,
            check=True,
        )
    count = require_unskipped_tests(output / "tests.xml")
    validate_reports(output)
    (output / "validation.json").write_text(
        json.dumps(
            {"version": version("insomnia-run"), "tests": count, "skipped": 0}, indent=2
        )
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    validate(Path(__file__).resolve().parents[1], args.output.resolve())


if __name__ == "__main__":
    main()
