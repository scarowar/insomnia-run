import os
import stat
from pathlib import Path

import pytest

from insomnia_run.report_files import (
    private_capture_directory,
    validate_destination,
    write_report_file,
)


@pytest.fixture
def action_environment(tmp_path):
    workspace = tmp_path / "workspace"
    temp = tmp_path / "temp"
    workspace.mkdir()
    temp.mkdir()
    return {
        "GITHUB_ACTIONS": "true",
        "GITHUB_WORKSPACE": str(workspace),
        "RUNNER_TEMP": str(temp),
        "GITHUB_OUTPUT": str(temp / "output"),
    }


def test_standalone_paths_are_not_confined(tmp_path):
    path = tmp_path / "nested" / "report.json"
    assert validate_destination(path, environ={}) == path
    assert write_report_file(path, "complete", environ={}) == path
    assert path.read_text() == "complete"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("root", ["GITHUB_WORKSPACE", "RUNNER_TEMP"])
def test_action_allows_new_nested_reports(action_environment, root):
    path = Path(action_environment[root]) / "reports" / "report.json"
    write_report_file(path, '{"complete": true}', environ=action_environment)
    assert path.read_text() == '{"complete": true}'
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "kind", ["outside", "root", "directory", "control", "nul", "empty"]
)
def test_action_rejects_unsafe_destinations(tmp_path, action_environment, kind):
    root = Path(action_environment["GITHUB_WORKSPACE"])
    paths = {
        "outside": tmp_path / "outside.json",
        "root": root,
        "directory": root / "directory",
        "control": action_environment["GITHUB_OUTPUT"],
        "nul": str(root / "bad\0name"),
        "empty": "",
    }
    (root / "directory").mkdir()
    with pytest.raises(ValueError):
        validate_destination(paths[kind], environ=action_environment)


@pytest.mark.parametrize(
    "variable",
    [
        "GITHUB_ENV",
        "GITHUB_PATH",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_STATE",
        "GITHUB_EVENT_PATH",
    ],
)
def test_all_control_files_are_protected(action_environment, variable):
    path = Path(action_environment["RUNNER_TEMP"]) / variable
    action_environment[variable] = str(path)
    with pytest.raises(ValueError):
        write_report_file(path, "bad", environ=action_environment)
    assert not path.exists()


def test_actions_requires_configured_allowed_roots(tmp_path):
    with pytest.raises(ValueError):
        validate_destination(tmp_path / "report", environ={"GITHUB_ACTIONS": "true"})


@pytest.mark.parametrize("link_target", ["file", "parent"])
def test_symlink_escape_is_rejected(tmp_path, action_environment, link_target):
    root = Path(action_environment["GITHUB_WORKSPACE"])
    outside = tmp_path / "outside"
    outside.mkdir()
    original = outside / "report"
    original.write_text("original")
    link = root / "link"
    link.symlink_to(original if link_target == "file" else outside)
    destination = link if link_target == "file" else link / "report"
    with pytest.raises(ValueError):
        write_report_file(destination, "bad", environ=action_environment)
    assert original.read_text() == "original"


def test_symlink_changed_after_preflight_is_rejected(tmp_path, action_environment):
    root = Path(action_environment["GITHUB_WORKSPACE"])
    directory = root / "reports"
    directory.mkdir()
    path = directory / "report"
    validate_destination(path, environ=action_environment)
    directory.rmdir()
    directory.symlink_to(tmp_path)
    with pytest.raises(ValueError):
        write_report_file(path, "bad", environ=action_environment)
    assert not (tmp_path / "report").exists()


def test_symlinks_within_allowed_roots_remain_supported(action_environment):
    root = Path(action_environment["GITHUB_WORKSPACE"])
    actual = root / "actual"
    actual.mkdir()
    (root / "alias").symlink_to(actual, target_is_directory=True)
    result = write_report_file(
        root / "alias" / "report", "safe", environ=action_environment
    )
    assert result == actual / "report"
    assert result.read_text() == "safe"


@pytest.mark.parametrize("kind", ["file", "parent"])
@pytest.mark.parametrize(
    "operation", [validate_destination, write_report_file], ids=["validate", "write"]
)
def test_symlink_loop_is_rejected_without_publishing(
    action_environment, kind, operation
):
    root = Path(action_environment["GITHUB_WORKSPACE"])
    link = root / "loop"
    link.symlink_to(link)
    destination = link if kind == "file" else link / "report.json"
    arguments = (
        (destination,) if operation is validate_destination else (destination, "bad")
    )
    with pytest.raises(ValueError, match="safely resolved"):
        operation(*arguments, environ=action_environment)
    assert link.is_symlink()


def test_parent_swap_after_validation_cannot_redirect_write(
    tmp_path, action_environment, monkeypatch
):
    import insomnia_run.report_files as report_files

    root = Path(action_environment["GITHUB_WORKSPACE"])
    directory = root / "reports"
    directory.mkdir()
    validate = report_files.validate_destination

    def swap_after_validation(*args, **kwargs):
        destination = validate(*args, **kwargs)
        directory.rmdir()
        directory.symlink_to(tmp_path)
        return destination

    monkeypatch.setattr(report_files, "validate_destination", swap_after_validation)
    with pytest.raises(OSError):
        write_report_file(directory / "report", "bad", environ=action_environment)
    assert not (tmp_path / "report").exists()


def test_parent_replaced_after_file_write_does_not_publish_to_new_directory(
    action_environment, monkeypatch
):
    root = Path(action_environment["GITHUB_WORKSPACE"])
    directory = root / "reports"
    directory.mkdir()
    moved = root / "moved"

    def swap_parent(_descriptor):
        directory.rename(moved)
        directory.mkdir()

    monkeypatch.setattr(os, "fsync", swap_parent)
    with pytest.raises(ValueError, match="parent changed"):
        write_report_file(directory / "report", "bad", environ=action_environment)
    assert list(directory.iterdir()) == []
    assert list(moved.iterdir()) == []


def test_destination_collisions_include_aliases_and_hardlinks(action_environment):
    root = Path(action_environment["GITHUB_WORKSPACE"])
    path = root / "report"
    path.write_text("original")
    alias = root / "alias"
    alias.hardlink_to(path)
    for collision in [path, root / "." / "report", alias]:
        with pytest.raises(ValueError):
            validate_destination(
                path, environ=action_environment, other_paths=[collision]
            )


def test_hardlink_to_control_file_is_rejected(action_environment):
    control = Path(action_environment["GITHUB_OUTPUT"])
    control.write_text("original")
    alias = Path(action_environment["GITHUB_WORKSPACE"]) / "alias"
    alias.hardlink_to(control)
    with pytest.raises(ValueError):
        write_report_file(alias, "bad", environ=action_environment)
    assert control.read_text() == "original"


def test_existing_report_is_replaced_with_restricted_complete_file(tmp_path):
    path = tmp_path / "report"
    path.write_text("old")
    path.chmod(0o644)
    old_inode = path.stat().st_ino
    write_report_file(path, "new\ncomplete", environ={})
    assert path.read_text() == "new\ncomplete"
    assert path.stat().st_ino != old_inode
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replace_keeps_original_and_cleans_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "report"
    path.write_text("old")

    def fail_replace(*args, **kwargs):
        raise OSError("simulated failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated failure"):
        write_report_file(path, "new", environ={})
    assert path.read_text() == "old"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("fail", [False, True])
def test_private_capture_directory_is_restricted_and_always_removed(tmp_path, fail):
    capture = None
    try:
        with private_capture_directory(parent=tmp_path) as capture:
            assert capture.parent == tmp_path
            assert stat.S_IMODE(capture.stat().st_mode) == 0o700
            write_report_file(capture / "native.json", "private", environ={})
            assert stat.S_IMODE((capture / "native.json").stat().st_mode) == 0o600
            if fail:
                raise RuntimeError("expected")
    except RuntimeError:
        assert fail
    assert capture is not None
    assert not capture.exists()
