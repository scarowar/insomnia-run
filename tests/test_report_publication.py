from xml.etree import ElementTree
import json

import pytest

from insomnia_run import main
from insomnia_run.models import (
    InsoResult,
    InsoRunReport,
    InsoStatus,
    RequestExecution,
    RunError,
)
from insomnia_run.privacy import Redactor
from insomnia_run.reporter import Reporter


def test_unused_raw_diagnostics_are_discarded_before_redaction(monkeypatch):
    observed = []
    original = Redactor.redact_report

    def redact(self, report):
        observed.append(report.raw_output)
        return original(self, report)

    monkeypatch.setattr(Redactor, "redact_report", redact)
    main._finalize_report(
        InsoRunReport(plan_end=0, raw_output="unused diagnostics"),
        workflow_url=None,
        include_raw_output=False,
        output_format=None,
        destinations={},
        redactor=Redactor(),
        annotations=False,
    )
    assert observed == [None]


def test_trusted_runner_url_survives_explicit_redaction(capsys):
    url = "https://github.com/owner/repo/actions/runs/12345678"
    main._finalize_report(
        InsoRunReport(plan_end=0),
        workflow_url=url,
        trusted_workflow_url=True,
        include_raw_output=False,
        output_format=None,
        destinations={},
        redactor=Redactor(["12345678"]),
        annotations=False,
    )
    assert url in capsys.readouterr().out


@pytest.mark.parametrize("error", [None, RunError(kind="timeout", message="Stopped")])
def test_junit_uses_wall_clock_time_for_empty_or_failed_runs(error):
    report = InsoRunReport(plan_end=0, duration_seconds=2.75, run_error=error)
    suite = ElementTree.fromstring(Reporter().generate_junit(report))
    assert suite.attrib["time"] == "2.75"


def test_annotations_identify_request_and_iteration(capsys):
    report = InsoRunReport(
        plan_end=1,
        executions=[RequestExecution(id=1, name="GET orders", iteration=1)],
        results=[
            InsoResult(
                id=1,
                execution_id=1,
                status=InsoStatus.FAIL,
                description="Status is 200",
            )
        ],
    )
    main._emit_annotations(report, err=True)
    text = capsys.readouterr().err
    assert "GET orders" in text
    assert "Iteration 2" in text
    assert "Status is 200" in text


@pytest.mark.parametrize(
    "secret", ["private-credential-value", "private-credential\nsecond-line-value"]
)
def test_raw_tail_is_bounded_after_redacting_secrets_at_the_boundary(tmp_path, secret):
    raw = "1..0\n" + secret + "x" * (1024 * 1024 - 10)
    destination = tmp_path / "report.json"
    main._finalize_report(
        InsoRunReport(plan_end=0, raw_output=raw),
        workflow_url=None,
        include_raw_output=True,
        output_format=None,
        destinations={"JSON": str(destination)},
        redactor=Redactor([secret]),
        annotations=False,
    )
    report = json.loads(destination.read_text())
    assert len(report["raw_output"].encode("utf-8")) <= 1024 * 1024
    assert "tial-value" not in report["raw_output"]
    assert "line-value" not in report["raw_output"]
