"""Execute the composite installer against local, verified release archives."""

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from urllib.error import HTTPError, URLError

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from install_runtime import download_archive  # noqa: E402

ACTION = yaml.safe_load((ROOT / "action.yml").read_text())
INSTALL = next(
    s["run"] for s in ACTION["runs"]["steps"] if s.get("name") == "Install Inso CLI"
)


@pytest.fixture
def installation(tmp_path):
    action_path = tmp_path / "action"
    scripts = action_path / "scripts"
    scripts.mkdir(parents=True)
    for name in ("verify_inso_release.py", "runtime_bundle.py", "install_runtime.py"):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
    source = tmp_path / "release.tar.xz"
    binary = b'#!/bin/bash\nprintf "13.3.1\\n"\n'
    with tarfile.open(source, "w:xz") as archive:
        member = tarfile.TarInfo("inso")
        member.size = len(binary)
        archive.addfile(member, io.BytesIO(binary))
    asset = "inso-linux-x64-13.3.1.tar.xz"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (action_path / "inso-checksums.json").write_text(json.dumps({asset: digest}))
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path),
        "ACTION_PATH": str(action_path),
        "PYTHON_BIN": sys.executable,
        "INSO_VERSION": "13.3.1",
        "INSO_ASSET": asset,
        "INSO_SHA256": digest,
        "INSO_ARCHIVE": str(source),
        "CUSTOM_DOWNLOAD_TOKEN": "",
        "CUSTOM_DOWNLOAD_ORIGIN": "",
        "PUBLIC_DOWNLOAD_TOKEN": "",
        "OFFLINE_INSTALL": "true",
    }

    def run(**updates):
        return subprocess.run(
            ["bash", "-euo", "pipefail", "-c", INSTALL],
            env={**env, **updates},
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    return run, env


def test_cold_install_and_verified_cache_hit(installation, tmp_path):
    run, _ = installation
    first = run()
    assert first.returncode == 0, first.stderr
    # A cache hit must not need the source archive again.
    (tmp_path / "release.tar.xz").unlink()
    second = run()
    assert second.returncode == 0, second.stderr
    binary = tmp_path / "insomnia-run-inso/bin/inso"
    assert subprocess.check_output([binary, "--version"], text=True) == "13.3.1\n"


def test_corrupt_cached_archive_fails_closed_and_preserves_previous_install(
    installation, tmp_path
):
    run, _ = installation
    assert run().returncode == 0
    cached = tmp_path / "insomnia-run-download/13.3.1/inso-linux-x64-13.3.1.tar.xz"
    cached.write_bytes(b"untrusted cache contents")
    second = run()
    assert second.returncode != 0
    assert "failed SHA-256" in second.stderr
    assert (
        subprocess.check_output([tmp_path / "insomnia-run-inso/bin/inso"], text=True)
        == "13.3.1\n"
    )


def test_tampered_download_is_rejected_before_extraction(installation, tmp_path):
    run, _ = installation
    (tmp_path / "release.tar.xz").write_bytes(b"tampered release")
    result = run()
    assert result.returncode != 0
    assert "failed SHA-256" in result.stderr
    assert not (tmp_path / "insomnia-run-inso/bin/inso").exists()
    assert not list((tmp_path / "insomnia-run-inso/bin").glob(".inso-*"))


def test_unbundled_version_uses_only_explicit_digest(installation, tmp_path):
    run, _ = installation
    (tmp_path / "action/inso-checksums.json").write_text("{}")
    result = run()
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "insomnia-run-release.json").exists()


def test_missing_digest_stops_before_copying_or_downloading(installation, tmp_path):
    run, _ = installation
    (tmp_path / "action/inso-checksums.json").write_text("{}")
    result = run(INSO_SHA256="")
    assert result.returncode != 0
    assert "inso-sha256" in result.stderr
    assert not (tmp_path / "insomnia-run-download").exists()


@pytest.mark.parametrize(
    "step_name", ["Validate Inso Version", "Resolve Inso archive identity"]
)
@pytest.mark.parametrize(
    "payload",
    [
        "invalid\n::warning::INJECTED",
        "invalid\r::error::INJECTED",
        "%0A::notice::INJECTED",
    ],
)
def test_invalid_version_is_not_echoed_as_a_workflow_command(
    installation, tmp_path, step_name, payload
):
    _, env = installation
    step = next(
        step for step in ACTION["runs"]["steps"] if step.get("name") == step_name
    )
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        env={
            **env,
            "INSO_VERSION": payload,
            "RUNNER_OS": "Linux",
            "RUNNER_ARCH": "X64",
        },
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode != 0
    assert "Invalid Inso" in result.stdout + result.stderr
    assert "INJECTED" not in result.stdout + result.stderr


@pytest.mark.parametrize("status", [403, 429, 401, 404, "disconnect"])
def test_release_download_errors_are_not_retried(tmp_path, monkeypatch, status):
    requests = []

    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            if status == "disconnect":
                raise URLError("private network detail")
            raise HTTPError(
                request.full_url,
                status,
                "private HTTP body",
                {},
                io.BytesIO(b"private"),
            )

    monkeypatch.setattr("install_runtime.build_opener", lambda handler: Opener())
    with pytest.raises(ValueError) as error:
        download_archive(
            "https://github.com/Kong/insomnia/releases/download/core%4013.3.1/inso.tar.xz",
            tmp_path / "archive",
        )
    assert len(requests) == 1
    assert "private" not in str(error.value)
    if status != "disconnect":
        assert f"HTTP {status}" in str(error.value)
        assert "not retried" in str(error.value)
    assert not (tmp_path / "archive").exists()


@pytest.mark.parametrize("relative", ["insomnia-run-download", "insomnia-run-inso"])
def test_composite_installer_rejects_symlink_escape(installation, tmp_path, relative):
    run, _ = installation
    external = tmp_path / "external"
    external.mkdir()
    runner = tmp_path / "runner"
    runner.mkdir()
    (runner / relative).symlink_to(external)
    result = run(RUNNER_TEMP=str(runner))
    assert result.returncode != 0
    assert "inside RUNNER_TEMP" in result.stderr
    assert not list(external.iterdir())


def test_custom_archive_forces_install_despite_matching_preinstalled_binary(
    installation, tmp_path
):
    _, env = installation
    preinstalled = tmp_path / "bin/inso"
    preinstalled.write_text('#!/bin/bash\nprintf "13.3.1\\n"\n')
    preinstalled.chmod(0o755)
    output = tmp_path / "github-output"
    detect = next(
        s["run"] for s in ACTION["runs"]["steps"] if s.get("name") == "Detect Inso CLI"
    )
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", detect],
        env={**env, "GITHUB_OUTPUT": str(output)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert output.read_text() == "found=false\n"


def test_verification_uses_current_preinstalled_binary_after_an_install(
    installation, tmp_path
):
    run, env = installation
    assert run().returncode == 0
    preinstalled = tmp_path / "bin/inso"
    preinstalled.write_text("#!/bin/bash\nprintf '12.2.0\\n'\n")
    preinstalled.chmod(0o755)
    verify = next(
        s["run"] for s in ACTION["runs"]["steps"] if s.get("name") == "Verify Inso CLI"
    )
    result = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", verify],
        env={**env, "INSO_VERSION": "12.2.0", "USE_INSTALLED_INSO": "false"},
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "12.2.0" in result.stdout
