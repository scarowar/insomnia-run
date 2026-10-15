import hashlib
import json
from pathlib import Path
import runpy

import pytest


HELPERS = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "inso_checksum.py")
)
expected_checksum = HELPERS["expected_checksum"]
verify_archive = HELPERS["verify_archive"]
release_paths = HELPERS["release_paths"]


@pytest.mark.parametrize(
    "asset",
    ["../inso-linux-x64-13.3.1.tar.xz", "inso-macos-../../secret.zip", "/tmp/secret"],
)
def test_asset_paths_cannot_escape_runner_temp(tmp_path, asset):
    with pytest.raises(ValueError, match="Invalid Inso release asset"):
        release_paths(asset, tmp_path)


@pytest.mark.parametrize(
    "filename", ["insomnia-run-release.json", "insomnia-run-download"]
)
def test_symlink_paths_cannot_escape_runner_temp(tmp_path, filename):
    root = tmp_path / "runner"
    root.mkdir()
    (root / filename).symlink_to(tmp_path)

    with pytest.raises(ValueError, match="inside RUNNER_TEMP"):
        release_paths("inso-linux-x64-13.3.1.tar.xz", root)


def test_release_paths_are_fixed_to_runner_temp(tmp_path):
    metadata, archive = release_paths("inso-macos-13.3.1-beta.1.zip", tmp_path)

    assert metadata == tmp_path / "insomnia-run-release.json"
    assert (
        archive
        == tmp_path / "insomnia-run-download/13.3.1-beta.1/inso-macos-13.3.1-beta.1.zip"
    )


def test_bundled_digest_needs_no_network_metadata(tmp_path):
    manifest = tmp_path / "checksums.json"
    manifest.write_text(json.dumps({"asset": "a" * 64}))

    assert expected_checksum("asset", manifest, None) == "a" * 64
    assert expected_checksum("unknown", manifest, None) == ""


@pytest.mark.parametrize("digest", [None, "sha512:" + "a" * 64, "sha256:invalid"])
def test_missing_or_invalid_official_digest_fails_closed(tmp_path, digest):
    manifest = tmp_path / "checksums.json"
    metadata = tmp_path / "release.json"
    manifest.write_text("{}")
    metadata.write_text(json.dumps({"assets": [{"name": "asset", "digest": digest}]}))

    with pytest.raises(ValueError):
        expected_checksum("asset", manifest, metadata)


def test_custom_version_uses_only_the_matching_official_asset(tmp_path):
    manifest = tmp_path / "checksums.json"
    metadata = tmp_path / "release.json"
    manifest.write_text("{}")
    metadata.write_text(
        json.dumps(
            {
                "assets": [
                    {"name": "other", "digest": "sha256:" + "a" * 64},
                    {"name": "asset", "digest": "sha256:" + "b" * 64},
                ]
            }
        )
    )

    assert expected_checksum("asset", manifest, metadata) == "b" * 64
    with pytest.raises(ValueError):
        expected_checksum("missing", manifest, metadata)


def test_corrupt_or_untrusted_archive_is_rejected(tmp_path):
    archive = tmp_path / "inso.tar.xz"
    archive.write_bytes(b"trusted archive")
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    verify_archive(archive, checksum)

    archive.write_bytes(b"tampered archive")
    with pytest.raises(ValueError, match="failed SHA-256"):
        verify_archive(archive, checksum)
    with pytest.raises(ValueError, match="trusted SHA-256"):
        verify_archive(archive, "")
