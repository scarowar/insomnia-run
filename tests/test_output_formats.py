from unittest.mock import Mock, patch
import pytest
from typer import BadParameter

from insomnia_run.main import _emit_machine_readable_output, _write_junit_output
from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus
from insomnia_run.reporter import Reporter


def test_emit_json_output_success():
    mock_report = Mock()
    mock_report.model_dump_json.return_value = '{"status": "passed"}'

    with patch("insomnia_run.main.typer.echo") as mock_echo:
        _emit_machine_readable_output(mock_report, "json")

    mock_report.model_dump_json.assert_called_once_with(indent=2)
    mock_echo.assert_called_once_with('{"status": "passed"}', err=True)


def test_emit_output_unsupported_format():
    with pytest.raises(BadParameter) as excinfo:
        _emit_machine_readable_output(Mock(), "xml")
    assert "Unsupported output format: 'xml'" in str(excinfo.value)


def test_emit_output_none_format():
    with patch("insomnia_run.main.typer.echo") as mock_echo:
        _emit_machine_readable_output(Mock(), None)
    mock_echo.assert_not_called()


def test_write_junit_output(tmp_path):
    report = InsoRunReport(
        plan_end=1,
        results=[InsoResult(id=1, status=InsoStatus.PASS, description="passes")],
    )
    output = tmp_path / "reports" / "insomnia-run.xml"

    _write_junit_output(Reporter(), report, str(output))

    assert output.exists()
    assert output.read_text(encoding="utf-8").startswith(
        '<?xml version="1.0" encoding="UTF-8"?>'
    )
    assert 'tests="1"' in output.read_text(encoding="utf-8")


def test_write_junit_output_is_optional(tmp_path):
    _write_junit_output(Reporter(), InsoRunReport(plan_end=0), None)

    assert list(tmp_path.iterdir()) == []
