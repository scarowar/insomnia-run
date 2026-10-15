"""Run the real installer with local release archives and a controlled downloader."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
ACTION = yaml.safe_load((ROOT / "action.yml").read_text())
INSTALL = next(
    s["run"] for s in ACTION["runs"]["steps"] if s.get("name") == "Install Inso CLI"
)


@pytest.fixture
def install_inso(tmp_path):
    action_path = tmp_path / "action"
    scripts = action_path / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/inso_checksum.py", scripts / "inso_checksum.py")
    source = tmp_path / "release.tar.xz"
    binary = b'#!/bin/bash\nprintf "13.3.1\\n"\n'
    with tarfile.open(source, "w:xz") as archive:
        member = tarfile.TarInfo("inso")
        member.size = len(binary)
        member.mode = 0o755
        archive.addfile(member, io.BytesIO(binary))
    asset = "inso-linux-x64-13.3.1.tar.xz"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (action_path / "inso-checksums.json").write_text(json.dumps({asset: digest}))
    metadata = tmp_path / "release.json"
    metadata.write_text(
        json.dumps({"assets": [{"name": asset, "digest": f"sha256:{digest}"}]})
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    commands = {
        "mkdir": '#!/bin/bash\nif [[ "$*" == "-p ${HOME}/.cache/pkg" ]]; then exit 0; fi\nexec /bin/mkdir "$@"\n',
        "curl": """#!/bin/bash
set -eu
out=""
while (( $# )); do
  if [[ "$1" == "--output" ]]; then out="$2"; shift; fi
  url="$1"
  shift
done
if [[ "$url" == https://api.github.com/* ]]; then
  echo metadata >> "$TEST_DOWNLOADS"
  cp "$TEST_METADATA" "$out"
else
  echo archive >> "$TEST_DOWNLOADS"
  cp "$TEST_SOURCE" "$out"
fi
""",
    }
    for name, script in commands.items():
        path = fake_bin / name
        path.write_text(script)
        path.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "ACTION_PATH": str(action_path),
        "INSO_VERSION": "13.3.1",
        "INSO_DOWNLOAD_TOKEN": "",
        "TEST_DOWNLOADS": str(tmp_path / "downloads"),
        "TEST_METADATA": str(metadata),
        "TEST_SOURCE": str(source),
    }

    def run():
        return subprocess.run(
            ["bash", "-eo", "pipefail", "-c", INSTALL],
            env=env,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    return run


def test_cold_install_and_verified_cache_hit(install_inso, tmp_path):
    first = install_inso()
    second = install_inso()

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "13.3.1" in second.stdout
    assert (tmp_path / "downloads").read_text().splitlines() == ["archive"]
    assert (tmp_path / "insomnia-run-inso/bin/inso").is_file()


def test_corrupt_cached_archive_is_downloaded_again(install_inso, tmp_path):
    first = install_inso()
    assert first.returncode == 0, first.stderr
    cached = tmp_path / "insomnia-run-download/13.3.1/inso-linux-x64-13.3.1.tar.xz"
    cached.write_bytes(b"untrusted cache contents")

    second = install_inso()

    assert second.returncode == 0, second.stderr
    assert "Cached Inso archive failed verification" in second.stdout
    assert (tmp_path / "downloads").read_text().splitlines() == ["archive", "archive"]


def test_tampered_download_is_rejected_before_extraction(install_inso, tmp_path):
    (tmp_path / "release.tar.xz").write_bytes(b"tampered release")

    result = install_inso()

    assert result.returncode != 0
    assert "failed SHA-256 verification" in result.stderr
    assert not (tmp_path / "insomnia-run-inso/bin/inso").exists()


def test_custom_version_resolves_the_official_release_digest(install_inso, tmp_path):
    (tmp_path / "action/inso-checksums.json").write_text("{}")

    result = install_inso()

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "downloads").read_text().splitlines() == ["metadata", "archive"]


def test_missing_release_digest_stops_before_downloading_binary(install_inso, tmp_path):
    (tmp_path / "action/inso-checksums.json").write_text("{}")
    (tmp_path / "release.json").write_text('{"assets": []}')

    result = install_inso()

    assert result.returncode != 0
    assert "no SHA-256 digest" in result.stderr
    assert (tmp_path / "downloads").read_text().splitlines() == ["metadata"]
