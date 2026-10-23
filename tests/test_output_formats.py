import json
from unittest.mock import Mock, patch
import pytest
from typer import BadParameter

from insomnia_run.main import (
    _emit_machine_readable_output,
    _validate_output_format,
)
from insomnia_run.models import InsoRunReport


def test_emit_json_output_success():
    mock_report = Mock()
    mock_report.model_dump_json.return_value = '{"status": "passed"}'

    with patch("insomnia_run.main.typer.echo") as mock_echo:
        _emit_machine_readable_output(mock_report, "json")

    mock_report.model_dump_json.assert_called_once_with(
        indent=2, exclude={"raw_output"}
    )
    mock_echo.assert_called_once_with('{"status": "passed"}', err=True)


@pytest.mark.parametrize("include_raw_output", [False, True])
def test_json_raw_logs_require_explicit_opt_in(capsys, include_raw_output):
    report = InsoRunReport(plan_end=0, raw_output="Authorization: secret")

    _emit_machine_readable_output(report, "json", include_raw_output=include_raw_output)

    payload = json.loads(capsys.readouterr().err)
    assert ("raw_output" in payload) is include_raw_output
    if include_raw_output:
        assert payload["raw_output"] == "Authorization: secret"


def test_emit_output_unsupported_format():
    report = Mock()
    with pytest.raises(BadParameter) as excinfo:
        _emit_machine_readable_output(report, "xml")
    assert "Unsupported output format: 'xml'" in str(excinfo.value)


def test_validate_output_unsupported_format():
    with pytest.raises(BadParameter) as excinfo:
        _validate_output_format("xml")
    assert "Unsupported output format: 'xml'" in str(excinfo.value)


def test_emit_output_none_format():
    with patch("insomnia_run.main.typer.echo") as mock_echo:
        _emit_machine_readable_output(Mock(), None)
    mock_echo.assert_not_called()
