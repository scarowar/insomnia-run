import os
from pathlib import Path
import stat
import sys
import tempfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import runtime_bundle


def mock_directory_metadata(monkeypatch, *, current_uid, directories):
    identities = {
        (path.stat().st_dev, path.stat().st_ino): (uid, mode)
        for path, uid, mode in directories
    }
    original = os.fstat

    def metadata(descriptor):
        value = original(descriptor)
        fields = list(value)
        fields[4] = current_uid
        identity = (value.st_dev, value.st_ino)
        if identity in identities:
            uid, mode = identities[identity]
            fields[4] = uid
            fields[0] = stat.S_IFDIR | mode
        return os.stat_result(fields)

    monkeypatch.setattr(os, "getuid", lambda: current_uid)
    monkeypatch.setattr(os, "fstat", metadata)


def test_root_owned_sticky_shared_temp_anchor_accepts_private_directory(
    tmp_path, monkeypatch
):
    anchor = tmp_path.parent
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(anchor))
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    mock_directory_metadata(
        monkeypatch, current_uid=1001, directories=[(anchor, 0, 0o1777)]
    )

    with runtime_bundle.open_directory(tmp_path / "private", create=True):
        pass

    assert (tmp_path / "private").is_dir()


@pytest.mark.parametrize("anchor_uid", [1001, 2001])
def test_nonroot_owned_sticky_writable_temp_anchor_is_rejected(
    tmp_path, monkeypatch, anchor_uid
):
    anchor = tmp_path.parent
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(anchor))
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    mock_directory_metadata(
        monkeypatch, current_uid=1001, directories=[(anchor, anchor_uid, 0o1777)]
    )

    with pytest.raises(ValueError, match="directory"):
        with runtime_bundle.open_directory(tmp_path / "private", create=True):
            pass

    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize("current_uid", [0, 1002])
def test_foreign_runner_temp_mount_is_trusted_only_for_container_root(
    tmp_path, monkeypatch, current_uid
):
    anchor = tmp_path / "runner-temp"
    anchor.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(anchor))
    mock_directory_metadata(
        monkeypatch, current_uid=current_uid, directories=[(anchor, 1001, 0o755)]
    )
    destination = anchor / "private"

    if current_uid == 0:
        with runtime_bundle.open_directory(destination, create=True):
            pass
        assert destination.is_dir()
    else:
        with pytest.raises(ValueError, match="directory"):
            with runtime_bundle.open_directory(destination, create=True):
                pass
        assert not destination.exists()


@pytest.mark.parametrize(
    ("child_uid", "child_mode"), [(1001, 0o700), (0, 0o770), (0, 0o1777)]
)
def test_container_root_still_rejects_unsafe_managed_subdirectories(
    tmp_path, monkeypatch, child_uid, child_mode
):
    anchor = tmp_path / "runner-temp"
    anchor.mkdir()
    child = anchor / "managed"
    child.mkdir()
    monkeypatch.setenv("RUNNER_TEMP", str(anchor))
    mock_directory_metadata(
        monkeypatch,
        current_uid=0,
        directories=[(anchor, 0, 0o755), (child, child_uid, child_mode)],
    )

    with pytest.raises(ValueError, match="directory"):
        with runtime_bundle.open_directory(child):
            pass


def test_resolved_shared_anchor_precedes_lexical_ancestors(tmp_path, monkeypatch):
    shared = tmp_path / "real-shared"
    shared.mkdir()
    alias = tmp_path / "temp-alias"
    alias.symlink_to(shared, target_is_directory=True)
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(alias))
    mock_directory_metadata(
        monkeypatch, current_uid=1001, directories=[(shared, 0, 0o1777)]
    )

    with runtime_bundle.open_directory(shared / "private", create=True):
        pass

    assert (shared / "private").is_dir()


def test_shared_ancestor_name_can_match_managed_directory_name(monkeypatch):
    monkeypatch.delenv("RUNNER_TEMP", raising=False)
    with tempfile.TemporaryDirectory(dir="/var/tmp") as directory:
        destination = Path(directory) / "tmp"
        with runtime_bundle.open_directory(destination, create=True):
            pass
        assert destination.is_dir()
