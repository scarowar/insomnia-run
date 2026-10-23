"""Trusted digests and action-managed installer path confinement."""

import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_inso_release import expected_digest, runner_path  # noqa: E402


@pytest.mark.parametrize("relative", ["insomnia-run-download", "insomnia-run-inso"])
def test_symlink_paths_cannot_escape_runner_temp(tmp_path, relative):
    root = tmp_path / "runner"
    root.mkdir()
    (root / relative).symlink_to(tmp_path)
    with pytest.raises(ValueError, match="inside RUNNER_TEMP"):
        runner_path(root / relative / "nested" / "file", root)


@pytest.mark.parametrize("relative", ["..", ".", "../runner-evil/archive"])
def test_path_must_be_strict_descendant_of_runner_temp(tmp_path, relative):
    root = tmp_path / "runner"
    root.mkdir()
    with pytest.raises(ValueError, match="inside RUNNER_TEMP"):
        runner_path(root / relative, root)


def test_release_paths_support_nonexistent_descendants(tmp_path):
    archive = tmp_path / "insomnia-run-download/13.3.1/inso-linux-x64-13.3.1.tar.xz"
    assert runner_path(archive, tmp_path) == archive


def test_bundled_digest_needs_no_network_metadata(tmp_path):
    manifest = tmp_path / "checksums.json"
    manifest.write_text(json.dumps({"asset": "a" * 64}))
    assert expected_digest("asset", manifest) == "a" * 64
    with pytest.raises(ValueError, match="inso-sha256"):
        expected_digest("unknown", manifest)


@pytest.mark.parametrize("digest", [None, "sha512:" + "a" * 64, "sha256:invalid", 123])
def test_missing_or_invalid_explicit_digest_fails_closed(tmp_path, digest):
    manifest = tmp_path / "checksums.json"
    manifest.write_text("{}")
    with pytest.raises(ValueError):
        expected_digest("asset", manifest, digest)


def test_custom_version_requires_independently_trusted_digest(tmp_path):
    manifest = tmp_path / "checksums.json"
    manifest.write_text("{}")
    assert expected_digest("asset", manifest, "b" * 64) == "b" * 64
    assert expected_digest("asset", manifest, "B" * 64) == "b" * 64


@pytest.mark.parametrize(
    "manifest_value", [[], {"asset": 123}, {"asset": "not-a-digest"}]
)
def test_invalid_bundled_checksum_manifest_is_rejected(tmp_path, manifest_value):
    manifest = tmp_path / "checksums.json"
    manifest.write_text(json.dumps(manifest_value))
    with pytest.raises(ValueError):
        expected_digest("asset", manifest)
