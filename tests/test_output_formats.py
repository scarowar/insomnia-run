from unittest.mock import Mock, patch

import pytest
from typer import BadParameter
from typer.testing import CliRunner

from insomnia_run.main import _emit_machine_readable_output, app


def test_emit_json_output_success():
    mock_report = Mock()
    mock_report.model_dump_json.return_value = '{"status": "passed"}'

    with patch("insomnia_run.main.typer.echo") as mock_echo:
        _emit_machine_readable_output(mock_report, "json")

    mock_report.model_dump_json.assert_called_once_with(indent=2)
    mock_echo.assert_called_once_with('{"status": "passed"}', err=True)


def test_validate_output_format_rejects_unsupported():
    from insomnia_run.main import _validate_output_format

    with pytest.raises(BadParameter) as excinfo:
        _validate_output_format("xml")
    assert "Unsupported output format: 'xml'" in str(excinfo.value)


def test_emit_output_never_raises_after_validation():
    _emit_machine_readable_output(Mock(), "xml")


def test_emit_output_none_format():
    with patch("insomnia_run.main.typer.echo") as mock_echo:
        _emit_machine_readable_output(Mock(), None)
    mock_echo.assert_not_called()


# --- Ticket 15: early format validation, JUnit output, raw-output knobs ---


@pytest.fixture
def no_runner(monkeypatch):
    """Fail the test if any runner actually executes."""
    from insomnia_run import main as main_module

    def _boom(*args, **kwargs):
        raise AssertionError("runner must not be called")

    monkeypatch.setattr(main_module.InsoRunner, "run_collection", _boom)
    monkeypatch.setattr(main_module.InsoRunner, "run_test", _boom)


class TestEarlyValidation:
    def test_bad_output_format_fails_before_running(self, no_runner):
        result = CliRunner().invoke(app, ["run-collection", "-w", "/x", "--output-format", "yaml"])
        assert result.exit_code == 2
        assert "Unsupported output format" in result.output


class TestJunitOutput:
    def test_junit_output_writes_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus

        captured = {}

        def fake_run(self, options):
            captured["options"] = options
            report = InsoRunReport(
                plan_end=1,
                results=[InsoResult(id=1, status=InsoStatus.FAIL, description="d", message="m")],
            )
            return report

        monkeypatch.setattr(main_module.InsoRunner, "run_collection", fake_run)
        junit_path = tmp_path / "junit.xml"

        result = CliRunner().invoke(
            app, ["run-collection", "-w", "/x", "--junit-output", str(junit_path)]
        )

        assert result.exit_code == 1
        assert junit_path.exists()
        assert "<failure" in junit_path.read_text()
        assert junit_path.read_text().startswith("<?xml")

    def test_junit_output_unwritable_path_is_loud(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoRunReport

        monkeypatch.setattr(
            main_module.InsoRunner,
            "run_collection",
            lambda self, options: InsoRunReport(plan_end=0),
        )
        blocker = tmp_path / "afile"
        blocker.write_text("not a directory")
        result = CliRunner().invoke(
            app,
            [
                "run-collection",
                "-w",
                "/x",
                "--junit-output",
                str(blocker / "j.xml"),
            ],
        )
        assert result.exit_code == 2
        assert "Cannot write JUnit output" in result.output


class TestAnnotationsAndRawFile:
    def test_annotations_emitted_only_in_github_actions(self, monkeypatch, tmp_path):
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoResult, InsoRunReport, InsoStatus

        report = InsoRunReport(
            plan_end=1,
            results=[InsoResult(id=1, status=InsoStatus.FAIL, description="d", message="m")],
        )
        monkeypatch.setattr(main_module.InsoRunner, "run_collection", lambda self, o: report)

        lines = []
        monkeypatch.setattr(
            main_module.typer, "echo", lambda msg, err=False: lines.append((msg, err))
        )

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        main_module.InsoRunner().run_collection = lambda o: report
        # direct unit call of the emitter:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        main_module._emit_annotations(report)
        assert lines == []

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        main_module._emit_annotations(report)
        assert lines == [("::error title=d::m", True)]

    def test_raw_output_file_writes_full_redacted_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoRunReport

        report = InsoRunReport(plan_end=0, raw_output="x" * 50)
        monkeypatch.setattr(main_module.InsoRunner, "run_collection", lambda self, o: report)
        raw_path = tmp_path / "raw.txt"

        result = CliRunner().invoke(
            app, ["run-collection", "-w", "/x", "--raw-output-file", str(raw_path)]
        )
        assert result.exit_code == 0
        assert raw_path.read_text() == "x" * 50


class TestCliOutputHandling:
    def test_junit_output_creates_parent_directories(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoRunReport

        monkeypatch.setattr(
            main_module.InsoRunner,
            "run_collection",
            lambda self, options: InsoRunReport(plan_end=0),
        )
        target = tmp_path / "deeply" / "nested" / "dir" / "junit.xml"
        result = CliRunner().invoke(
            app, ["run-collection", "-w", "/x", "--junit-output", str(target)]
        )
        assert result.exit_code == 0
        assert target.exists()

    def test_junit_output_failure_when_parent_is_a_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoRunReport

        monkeypatch.setattr(
            main_module.InsoRunner,
            "run_collection",
            lambda self, options: InsoRunReport(plan_end=0),
        )
        blocker = tmp_path / "afile"
        blocker.write_text("not a directory")
        result = CliRunner().invoke(
            app, ["run-collection", "-w", "/x", "--junit-output", str(blocker / "j.xml")]
        )
        assert result.exit_code == 2
        assert "Cannot write JUnit output" in result.output

    def test_short_env_var_value_warns(self, monkeypatch):
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoRunReport

        monkeypatch.setattr(
            main_module.InsoRunner,
            "run_collection",
            lambda self, options: InsoRunReport(plan_end=0),
        )
        result = CliRunner().invoke(app, ["run-collection", "-w", "/x", "--env-var", "K=ab"])
        assert result.exit_code == 0
        assert "will not be redacted" in result.output

    def test_invalid_env_var_format_is_rejected(self):
        result = CliRunner().invoke(app, ["run-collection", "-w", "/x", "--env-var", "BADFORMAT"])
        assert result.exit_code == 2
        assert "Invalid env-var format" in result.output

    def test_run_test_junit_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoRunReport

        monkeypatch.setattr(
            main_module.InsoRunner, "run_test", lambda self, o: InsoRunReport(plan_end=0)
        )
        target = tmp_path / "junit-test.xml"
        result = CliRunner().invoke(app, ["run-test", "-w", "/x", "--junit-output", str(target)])
        assert result.exit_code == 0
        assert target.exists()
        assert "<?xml" in target.read_text()

    def test_raw_output_file_not_created_when_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path))
        from insomnia_run import main as main_module
        from insomnia_run.models import InsoRunReport

        monkeypatch.setattr(
            main_module.InsoRunner,
            "run_collection",
            lambda self, o: InsoRunReport(plan_end=0, raw_output=None),
        )
        raw_path = tmp_path / "raw.txt"
        result = CliRunner().invoke(
            app, ["run-collection", "-w", "/x", "--raw-output-file", str(raw_path)]
        )
        assert result.exit_code == 0
        assert not raw_path.exists()

    def test_validate_output_path_rejects_outside_workspace(self, tmp_path, monkeypatch):
        from insomnia_run.main import _validate_output_path

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.setenv("GITHUB_WORKSPACE", str(tmp_path / "ws"))
        monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "rt"))
        (tmp_path / "ws").mkdir()
        (tmp_path / "rt").mkdir()
        with pytest.raises(BadParameter, match="must be inside GITHUB_WORKSPACE"):
            _validate_output_path("/etc/passwd", "JUnit output")

    def test_validate_output_path_empty_roots_rejected(self, monkeypatch):
        from insomnia_run.main import _validate_output_path

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        monkeypatch.delenv("GITHUB_WORKSPACE", raising=False)
        monkeypatch.delenv("RUNNER_TEMP", raising=False)
        with pytest.raises(BadParameter, match="cannot validate"):
            _validate_output_path("/tmp/x", "raw output")

    def test_validate_output_path_allows_any_outside_actions(self, tmp_path, monkeypatch):
        from insomnia_run.main import _validate_output_path

        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        p = _validate_output_path(str(tmp_path / "anywhere" / "file.txt"), "JUnit output")
        assert str(p).endswith("file.txt")
