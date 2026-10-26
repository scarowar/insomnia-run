import importlib.util
from html import escape
import json
from pathlib import Path
import sys

import pytest


@pytest.fixture
def validator():
    if sys.version_info < (3, 11):
        pytest.skip("Release validation uses tomllib on Python 3.11+")
    spec = importlib.util.spec_from_file_location(
        "validate_release",
        Path(__file__).resolve().parents[1] / "scripts/validate_release.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("attribute", ["skipped", "failures", "errors"])
def test_release_evidence_rejects_skips_and_unsuccessful_tests(
    validator, tmp_path, attribute
):
    path = tmp_path / "tests.xml"
    path.write_text(f'<testsuites><testsuite tests="1" {attribute}="1"/></testsuites>')
    with pytest.raises(ValueError, match="without skips"):
        validator.require_unskipped_tests(path)


def test_release_evidence_rejects_empty_or_missing_critical_suite(validator, tmp_path):
    path = tmp_path / "tests.xml"
    path.write_text('<testsuites><testsuite tests="0"/></testsuites>')
    with pytest.raises(ValueError, match="without skips"):
        validator.require_unskipped_tests(path)
    path.write_text(
        '<testsuites><testsuite tests="1"><testcase classname="unrelated"/></testsuite></testsuites>'
    )
    with pytest.raises(ValueError, match="did not execute"):
        validator.require_unskipped_tests(path)


def test_release_evidence_requires_each_real_integration_family(validator, tmp_path):
    classes = [
        "test_patch_regressions",
        "test_reporting_experience",
        "test_process_environment",
        "test_inso_compatibility",
        "test_native_compatibility",
        "test_managed_python",
        "test_release_tools",
    ]
    path = tmp_path / "tests.xml"
    cases = "".join(f'<testcase classname="tests.{name}"/>' for name in classes)
    path.write_text(
        f'<testsuites><testsuite tests="{len(classes)}">{cases}</testsuite></testsuites>'
    )
    assert validator.require_unskipped_tests(path) == len(classes)
    cases = "".join(
        f'<testcase classname="tests.{name}"/>'
        for name in classes
        if name != "test_process_environment"
    )
    path.write_text(
        f'<testsuites><testsuite tests="{len(classes) - 1}">{cases}</testsuite></testsuites>'
    )
    with pytest.raises(ValueError, match="did not execute test_process_environment"):
        validator.require_unskipped_tests(path)


def test_rendered_report_validation_retains_machine_and_human_evidence(
    validator, tmp_path, monkeypatch
):
    from markdown_it import MarkdownIt

    monkeypatch.setattr(validator, "render_gfm", MarkdownIt().enable("table").render)
    validator.validate_reports(tmp_path)
    assert len(list(tmp_path.glob("*.html"))) == 4
    assert (tmp_path / "mixed.json").is_file()
    assert (tmp_path / "mixed.xml").is_file()
    assert (tmp_path / "report-checks.json").is_file()
    hostile = (tmp_path / "hostile.html").read_text()
    assert "View raw output" in hostile
    assert "<img" not in hostile
    assert "<script" not in hostile


def test_rendered_report_validation_rejects_missing_request_in_renderer(
    validator, tmp_path, monkeypatch
):
    monkeypatch.setattr(validator, "render_gfm", lambda markdown: "empty")
    with pytest.raises(ValueError, match="lost an executed request"):
        validator.validate_reports(tmp_path)


def test_rendered_report_validation_checks_exact_request_identity(
    validator, tmp_path, monkeypatch
):
    from markdown_it import MarkdownIt

    monkeypatch.setattr(
        validator,
        "render_gfm",
        lambda markdown: (
            MarkdownIt()
            .enable("table")
            .render(markdown)
            .replace("<code>request-1</code>", "<code>request-10</code>")
        ),
    )
    with pytest.raises(ValueError, match="lost an executed request"):
        validator.validate_reports(tmp_path)


def inject_publication_text(validator, monkeypatch, artifact, text):
    from insomnia_run.models import InsoRunReport
    from insomnia_run.reporter import Reporter
    from markdown_it import MarkdownIt

    render = MarkdownIt("commonmark").enable("table").render
    monkeypatch.setattr(validator, "render_gfm", render)
    comment = "\n<!-- " + text + " -->\n"
    if artifact == "html":
        monkeypatch.setattr(
            validator, "render_gfm", lambda markdown: render(markdown) + comment
        )
    elif artifact == "json":
        original = InsoRunReport.model_dump_json

        def serialize(report, *args, **kwargs):
            payload = json.loads(original(report, *args, **kwargs))
            payload["publication_probe"] = text
            return json.dumps(payload)

        monkeypatch.setattr(InsoRunReport, "model_dump_json", serialize)
    else:
        method = "generate_markdown" if artifact == "markdown" else "generate_junit"
        original = getattr(Reporter, method)

        def serialize(reporter, *args, **kwargs):
            return original(reporter, *args, **kwargs) + comment

        monkeypatch.setattr(Reporter, method, serialize)


@pytest.mark.parametrize("artifact", ["json", "markdown", "junit", "html"])
@pytest.mark.parametrize(
    "escape_depth", [0, 1, 2], ids=["raw", "escaped", "double-escaped"]
)
def test_report_validation_rejects_complete_credentials_in_serialized_forms(
    validator, tmp_path, monkeypatch, artifact, escape_depth
):
    credential = "synthetic&credential+value"
    for _ in range(escape_depth):
        credential = escape(credential)
    inject_publication_text(validator, monkeypatch, artifact, credential)
    with pytest.raises(ValueError, match="credential survived"):
        validator.validate_reports(tmp_path)


@pytest.mark.parametrize("artifact", ["json", "markdown", "junit", "html"])
@pytest.mark.parametrize("fragment", ["synthetic", "credential+value"])
def test_report_validation_accepts_unrelated_words_and_credential_fragments(
    validator, tmp_path, monkeypatch, artifact, fragment
):
    inject_publication_text(validator, monkeypatch, artifact, fragment)
    validator.validate_reports(tmp_path)
    assert (tmp_path / "report-checks.json").is_file()


def test_release_preflight_rejects_editable_source(validator, tmp_path, monkeypatch):
    import insomnia_run

    monkeypatch.setattr(
        insomnia_run, "__file__", str(tmp_path / "src/insomnia_run/__init__.py")
    )
    with pytest.raises(ValueError, match="installed wheel"):
        validator.require_installed_wheel(tmp_path)


def test_release_preflight_rejects_stale_version_and_stale_source(
    validator, tmp_path, monkeypatch
):
    import insomnia_run

    (tmp_path / "pyproject.toml").write_text('[project]\nversion="0.2.1"\n')
    installed = tmp_path / "installed"
    installed.mkdir()
    (installed / "__init__.py").write_text("VALUE = 1\n")
    source = tmp_path / "src/insomnia_run"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("VALUE = 2\n")
    monkeypatch.setattr(insomnia_run, "__file__", str(installed / "__init__.py"))
    monkeypatch.setattr(validator, "version", lambda name: "0.2.0")
    with pytest.raises(ValueError, match="version differs"):
        validator.require_installed_wheel(tmp_path)
    monkeypatch.setattr(validator, "version", lambda name: "0.2.1")
    with pytest.raises(ValueError, match="source differs"):
        validator.require_installed_wheel(tmp_path)
    (installed / "__init__.py").write_bytes((source / "__init__.py").read_bytes())
    validator.require_installed_wheel(tmp_path)


@pytest.mark.parametrize("runner_temp", [False, True])
def test_release_suite_uses_runner_temporary_directory(
    validator, tmp_path, monkeypatch, runner_temp
):
    if runner_temp:
        monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    else:
        monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(validator, "require_installed_wheel", lambda root: None)
    scratch_paths = []

    def inspect(command, **kwargs):
        scratch = Path(command[command.index("--basetemp") + 1]).parent
        assert scratch.is_dir()
        if runner_temp:
            assert scratch.parent == tmp_path
        scratch_paths.append(scratch)
        raise RuntimeError("pytest boundary reached")

    monkeypatch.setattr(validator.subprocess, "run", inspect)
    with pytest.raises(RuntimeError, match="pytest boundary reached"):
        validator.validate(tmp_path, tmp_path / "evidence")
    assert len(scratch_paths) == 1
    assert not scratch_paths[0].exists()
